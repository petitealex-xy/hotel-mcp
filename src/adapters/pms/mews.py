"""
Mews PMS adapter.

Uses Mews Connector API v1 (REST/JSON).
Authentication: AccessToken passed in every request body.
Sandbox base URL: https://api.mews-demo.com
Production base URL: https://api.mews.com

Reference: https://mews-systems.gitbook.io/connector-api
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.adapters.pms.base import (
    BasePMSAdapter,
    GuestNotFound,
    RateLimitExceeded,
    ReservationNotFound,
    UpstreamUnavailable,
)
from src.config import PMSConfig
from src.models.guest import Gender, LoyaltyTier, PMSGuest
from src.models.reservation import (
    GuestCount,
    RateDetail,
    RateType,
    Reservation,
    ReservationStatus,
)
from src.models.room import HousekeepingStatus, Room, RoomStatus

logger = logging.getLogger(__name__)

# Mews sandbox credentials (override with real ones in production)
MEWS_SANDBOX_URL = "https://api.mews-demo.com"
MEWS_PRODUCTION_URL = "https://api.mews.com"


class MewsAdapter(BasePMSAdapter):
    """
    Mews Connector API adapter.

    All requests are POST with JSON body containing AccessToken.
    Mews uses GUIDs for all IDs.
    """

    def __init__(self, config: PMSConfig) -> None:
        self._config = config
        self._base_url = (
            MEWS_SANDBOX_URL if "demo" in config.base_url else MEWS_PRODUCTION_URL
        )
        if config.base_url:
            self._base_url = config.base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._config.timeout_seconds,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def _auth(self) -> dict:
        """Base auth payload included in every Mews request."""
        return {
            "ClientToken": "E0D439EE522F44368DC78E1BFB03710C-D24FB11DBE31D4621C4817E028D9E1D",
            "AccessToken": self._config.api_key,
            "Client": "HotelMCP/1.0",
        }

    async def _post(self, path: str, body: dict) -> dict:
        client = await self._get_client()
        payload = {**self._auth(), **body}

        try:
            resp = await client.post(path, json=payload)
        except httpx.ConnectError as exc:
            raise UpstreamUnavailable(f"Cannot reach Mews: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitExceeded("Mews rate limit hit")
        if resp.status_code >= 500:
            raise UpstreamUnavailable(f"Mews 5xx: {resp.status_code}")

        resp.raise_for_status()
        return resp.json()

    # ── Field normalisation ───────────────────────────────────────────────────

    @staticmethod
    def _map_gender(mews_gender: str | None) -> Gender:
        return {
            "Male": Gender.MALE,
            "Female": Gender.FEMALE,
        }.get(mews_gender or "", Gender.UNKNOWN)

    @staticmethod
    def _map_reservation_status(mews_state: str) -> ReservationStatus:
        return {
            "Confirmed": ReservationStatus.CONFIRMED,
            "Started": ReservationStatus.CHECKED_IN,
            "Processed": ReservationStatus.CHECKED_OUT,
            "Canceled": ReservationStatus.CANCELLED,
        }.get(mews_state, ReservationStatus.CONFIRMED)

    @staticmethod
    def _map_room_status(mews_state: str) -> RoomStatus:
        return {
            "Dirty": RoomStatus.VACANT,
            "Clean": RoomStatus.VACANT,
            "Inspected": RoomStatus.VACANT,
            "OutOfOrder": RoomStatus.OUT_OF_ORDER,
            "OutOfService": RoomStatus.OUT_OF_SERVICE,
        }.get(mews_state, RoomStatus.VACANT)

    @staticmethod
    def _map_housekeeping(mews_state: str) -> HousekeepingStatus:
        return {
            "Dirty": HousekeepingStatus.DIRTY,
            "Clean": HousekeepingStatus.CLEAN,
            "Inspected": HousekeepingStatus.INSPECTED,
            "OutOfOrder": HousekeepingStatus.OUT_OF_ORDER,
        }.get(mews_state, HousekeepingStatus.DIRTY)

    def _parse_customer(self, customer: dict) -> PMSGuest:
        name = customer.get("LastName", "")
        first = customer.get("FirstName", "")
        emails = customer.get("Email", "")
        phone = customer.get("Phone", "")
        dob = customer.get("BirthDate")
        nationality = customer.get("NationalityCode")

        return PMSGuest(
            pms_id=customer["Id"],
            property_id=self._config.property_id,
            first_name=first,
            last_name=name,
            email=emails if emails else None,
            phone=phone if phone else None,
            date_of_birth=date.fromisoformat(dob[:10]) if dob else None,
            gender=self._map_gender(customer.get("Sex")),
            nationality=nationality,
            loyalty_number=customer.get("LoyaltyCode"),
            loyalty_tier=LoyaltyTier.NONE,
            total_stays=customer.get("NumberOfReservations", 0),
            source_system="mews",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, str]:
        try:
            await self._post("/api/connector/v1/configuration/get", {})
            return {"status": "ok", "system": "mews"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    @retry(
        retry=retry_if_exception_type(UpstreamUnavailable),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_guest_by_id(self, guest_id: str) -> PMSGuest:
        data = await self._post(
            "/api/connector/v1/customers/getAll",
            {"CustomerIds": [guest_id], "Extent": {"Customers": True}},
        )
        customers = data.get("Customers", [])
        if not customers:
            raise GuestNotFound(f"Mews: guest {guest_id!r} not found")
        return self._parse_customer(customers[0])

    async def get_guest_by_email(self, email: str) -> PMSGuest:
        data = await self._post(
            "/api/connector/v1/customers/getAll",
            {"Emails": [email], "Extent": {"Customers": True}},
        )
        customers = data.get("Customers", [])
        if not customers:
            raise GuestNotFound(f"Mews: no guest with email {email!r}")
        return self._parse_customer(customers[0])

    async def search_guests(self, query: str, limit: int = 20) -> list[PMSGuest]:
        data = await self._post(
            "/api/connector/v1/customers/getAll",
            {
                "NameOrEmail": query,
                "Extent": {"Customers": True},
                "Limitation": {"Count": limit},
            },
        )
        return [self._parse_customer(c) for c in data.get("Customers", [])]

    async def get_reservation(self, reservation_id: str) -> Reservation:
        data = await self._post(
            "/api/connector/v1/reservations/getAll",
            {
                "ReservationIds": [reservation_id],
                "Extent": {
                    "Reservations": True,
                    "Customers": True,
                    "Rates": True,
                },
            },
        )
        reservations = data.get("Reservations", [])
        if not reservations:
            raise ReservationNotFound(f"Mews: reservation {reservation_id!r} not found")

        r = reservations[0]
        arrival = r.get("StartUtc", "")[:10]
        departure = r.get("EndUtc", "")[:10]

        return Reservation(
            reservation_id=reservation_id,
            confirmation_number=r.get("Number", reservation_id),
            property_id=self._config.property_id,
            pms_guest_id=r.get("CustomerId", ""),
            guest_name=r.get("CustomerName", ""),
            arrival_date=date.fromisoformat(arrival) if arrival else date.today(),
            departure_date=date.fromisoformat(departure) if departure else date.today(),
            room_number=r.get("RoomId"),
            room_type_booked=r.get("RequestedCategoryId", ""),
            guest_count=GuestCount(
                adults=r.get("AdultCount", 1),
                children=r.get("ChildCount", 0),
            ),
            rate=RateDetail(
                rate_code=r.get("RateId", "BAR"),
                rate_type=RateType.BAR,
                daily_rate=r.get("TotalAmount", {}).get("Value", 0.0),
                currency=r.get("TotalAmount", {}).get("Currency", "EUR"),
            ),
            status=self._map_reservation_status(r.get("State", "Confirmed")),
            source_system="mews",
        )

    async def get_reservations_for_guest(
        self, guest_id: str, limit: int = 10
    ) -> list[Reservation]:
        data = await self._post(
            "/api/connector/v1/reservations/getAll",
            {
                "CustomerIds": [guest_id],
                "Extent": {"Reservations": True},
                "Limitation": {"Count": limit},
            },
        )
        results = []
        for r in data.get("Reservations", []):
            try:
                results.append(await self.get_reservation(r["Id"]))
            except ReservationNotFound:
                continue
        return results

    async def get_room(self, room_number: str, property_id: str) -> Room:
        data = await self._post(
            "/api/connector/v1/spaces/getAll",
            {"Extent": {"Spaces": True, "SpaceFeatures": True}},
        )
        spaces = data.get("Spaces", [])
        room_data = next(
            (s for s in spaces if s.get("Number") == room_number), None
        )
        if not room_data:
            from src.adapters.pms.base import AdapterError
            raise AdapterError(f"Mews: room {room_number!r} not found")

        hk_state = room_data.get("State", "Dirty")
        return Room(
            room_number=room_number,
            property_id=property_id,
            floor=room_data.get("FloorNumber"),
            room_type=room_data.get("SpaceCategoryId", ""),
            room_status=self._map_room_status(hk_state),
            housekeeping_status=self._map_housekeeping(hk_state),
            accessible=room_data.get("IsAccessible", False),
            source_system="mews",
        )

    async def list_rooms(
        self,
        property_id: str,
        floor: str | None = None,
        room_type: str | None = None,
        limit: int = 100,
    ) -> list[Room]:
        data = await self._post(
            "/api/connector/v1/spaces/getAll",
            {"Extent": {"Spaces": True}},
        )
        spaces = data.get("Spaces", [])
        rooms = []
        for s in spaces[:limit]:
            if floor and s.get("FloorNumber") != floor:
                continue
            if room_type and s.get("SpaceCategoryId") != room_type:
                continue
            hk_state = s.get("State", "Dirty")
            rooms.append(Room(
                room_number=s.get("Number", ""),
                property_id=property_id,
                floor=s.get("FloorNumber"),
                room_type=s.get("SpaceCategoryId", ""),
                room_status=self._map_room_status(hk_state),
                housekeeping_status=self._map_housekeeping(hk_state),
                accessible=s.get("IsAccessible", False),
                source_system="mews",
            ))
        return rooms
