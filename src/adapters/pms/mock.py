"""
In-memory mock PMS adapter.
Used in tests, local development, and demos when no real PMS is configured.
Seed data covers the most common reconciliation scenarios.
"""

from __future__ import annotations

from datetime import date, datetime

from src.adapters.pms.base import BasePMSAdapter, GuestNotFound, ReservationNotFound
from src.models.guest import Gender, LoyaltyTier, PMSGuest
from src.models.reservation import (
    GuestCount,
    RateDetail,
    RateType,
    Reservation,
    ReservationStatus,
    SpecialRequest,
)
from src.models.room import HousekeepingStatus, Room, RoomStatus

_GUESTS: dict[str, PMSGuest] = {
    "PMS-001": PMSGuest(
        pms_id="PMS-001",
        property_id="HOTEL-PARIS-01",
        first_name="Marie",
        last_name="Dupont",
        email="marie.dupont@example.com",
        phone="+33612345678",
        date_of_birth=date(1985, 6, 15),
        gender=Gender.FEMALE,
        nationality="FR",
        loyalty_number="LYL-99001",
        loyalty_tier=LoyaltyTier.GOLD,
        total_stays=14,
        total_revenue=8_420.0,
        currency="EUR",
        last_stay_date=date(2024, 3, 12),
        source_system="mock_pms",
    ),
    "PMS-002": PMSGuest(
        pms_id="PMS-002",
        property_id="HOTEL-PARIS-01",
        first_name="James",
        last_name="O'Brien",
        email="james.obrien@corporate.ie",
        phone="+35312345678",
        nationality="IE",
        loyalty_tier=LoyaltyTier.SILVER,
        loyalty_number="LYL-99002",
        total_stays=3,
        total_revenue=1_650.0,
        currency="EUR",
        source_system="mock_pms",
    ),
    "PMS-003": PMSGuest(
        # Deliberate mismatches vs CRM-003 for reconciliation demos
        pms_id="PMS-003",
        property_id="HOTEL-PARIS-01",
        first_name="Yuki",
        last_name="Tanaka",
        email="y.tanaka@example.jp",       # different from CRM
        phone="+81901234567",
        nationality="JP",
        loyalty_number="LYL-99003",
        loyalty_tier=LoyaltyTier.PLATINUM,
        total_stays=22,
        total_revenue=42_000.0,
        currency="EUR",
        source_system="mock_pms",
    ),
}

_RESERVATIONS: dict[str, Reservation] = {
    "RES-2024-001": Reservation(
        reservation_id="RES-2024-001",
        confirmation_number="CONF-8812",
        property_id="HOTEL-PARIS-01",
        pms_guest_id="PMS-001",
        guest_name="Marie Dupont",
        arrival_date=date(2024, 6, 1),
        departure_date=date(2024, 6, 5),
        room_number="512",
        room_type_booked="DELUXE_KING",
        room_type_assigned="DELUXE_KING",
        guest_count=GuestCount(adults=2),
        rate=RateDetail(
            rate_code="CORP25",
            rate_type=RateType.CORPORATE,
            daily_rate=195.0,
            currency="EUR",
            includes_breakfast=True,
        ),
        total_charges=780.0,
        total_paid=780.0,
        balance_due=0.0,
        status=ReservationStatus.CHECKED_OUT,
        booking_channel="direct",
        is_vip=True,
        special_requests=[
            SpecialRequest(
                category="celebration",
                description="Wedding anniversary — please arrange champagne",
                fulfilled=True,
            )
        ],
        source_system="mock_pms",
    ),
}

_ROOMS: dict[str, Room] = {
    "512": Room(
        room_number="512",
        property_id="HOTEL-PARIS-01",
        floor="5",
        room_type="DELUXE_KING",
        room_type_label="Deluxe King Room",
        room_status=RoomStatus.VACANT,
        housekeeping_status=HousekeepingStatus.INSPECTED,
        last_cleaned_at=datetime(2024, 5, 30, 10, 0),
        bed_configuration="King",
        max_occupancy=2,
        accessible=False,
        smoking=False,
        source_system="mock_pms",
    ),
    "301": Room(
        room_number="301",
        property_id="HOTEL-PARIS-01",
        floor="3",
        room_type="TWIN",
        room_type_label="Classic Twin Room",
        room_status=RoomStatus.OCCUPIED,
        housekeeping_status=HousekeepingStatus.DO_NOT_DISTURB,
        reservation_id="RES-2024-999",
        guest_name="John Smith",
        bed_configuration="Twin",
        max_occupancy=2,
        source_system="mock_pms",
    ),
    "118": Room(
        room_number="118",
        property_id="HOTEL-PARIS-01",
        floor="1",
        room_type="ACCESSIBLE_KING",
        room_type_label="Accessible King Room",
        room_status=RoomStatus.VACANT,
        housekeeping_status=HousekeepingStatus.DIRTY,
        priority_clean=True,
        accessible=True,
        source_system="mock_pms",
    ),
}


class MockPMSAdapter(BasePMSAdapter):
    async def health_check(self) -> dict[str, str]:
        return {"status": "ok", "system": "mock_pms"}

    async def get_guest_by_id(self, guest_id: str) -> PMSGuest:
        if guest_id not in _GUESTS:
            raise GuestNotFound(f"Mock PMS: guest {guest_id!r} not found")
        return _GUESTS[guest_id]

    async def get_guest_by_email(self, email: str) -> PMSGuest:
        for g in _GUESTS.values():
            if g.email and g.email.lower() == email.lower():
                return g
        raise GuestNotFound(f"Mock PMS: no guest with email {email!r}")

    async def search_guests(self, query: str, limit: int = 20) -> list[PMSGuest]:
        q = query.lower()
        results = [
            g for g in _GUESTS.values()
            if q in g.first_name.lower()
            or q in g.last_name.lower()
            or (g.email and q in g.email.lower())
        ]
        return results[:limit]

    async def get_reservation(self, reservation_id: str) -> Reservation:
        if reservation_id not in _RESERVATIONS:
            raise ReservationNotFound(f"Mock PMS: reservation {reservation_id!r} not found")
        return _RESERVATIONS[reservation_id]

    async def get_reservations_for_guest(
        self, guest_id: str, limit: int = 10
    ) -> list[Reservation]:
        return [r for r in _RESERVATIONS.values() if r.pms_guest_id == guest_id][:limit]

    async def get_room(self, room_number: str, property_id: str) -> Room:
        if room_number not in _ROOMS:
            from src.adapters.pms.base import AdapterError
            raise AdapterError(f"Mock PMS: room {room_number!r} not found")
        return _ROOMS[room_number]

    async def list_rooms(
        self,
        property_id: str,
        floor: str | None = None,
        room_type: str | None = None,
        limit: int = 100,
    ) -> list[Room]:
        rooms = list(_ROOMS.values())
        if floor:
            rooms = [r for r in rooms if r.floor == floor]
        if room_type:
            rooms = [r for r in rooms if r.room_type == room_type]
        return rooms[:limit]
