"""
Abstract PMS adapter.

Every PMS integration (OPERA, Cloudbeds, Mews, Apaleo …) must subclass
this and implement the abstract methods. The tools layer talks only to
this interface — PMS-specific API quirks stay inside each adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.guest import PMSGuest
from src.models.reservation import Reservation
from src.models.room import Room


class AdapterError(Exception):
    """Base error for all adapter failures."""


class GuestNotFound(AdapterError):
    """Raised when the guest cannot be located in the remote system."""


class ReservationNotFound(AdapterError):
    """Raised when the reservation cannot be located."""


class RateLimitExceeded(AdapterError):
    """Raised when the upstream API signals rate limiting (429)."""


class UpstreamUnavailable(AdapterError):
    """Raised for network errors or 5xx responses from the upstream API."""


class BasePMSAdapter(ABC):
    """
    Contract that all PMS connectors must fulfil.

    All methods are async so they can be awaited directly in MCP tool
    handlers without blocking the event loop.
    """

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    async def health_check(self) -> dict[str, str]:
        """Return {"status": "ok"} or raise UpstreamUnavailable."""

    # ── Guest operations ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_guest_by_id(self, guest_id: str) -> PMSGuest:
        """Fetch a guest profile by the PMS's native guest ID."""

    @abstractmethod
    async def get_guest_by_email(self, email: str) -> PMSGuest:
        """Fetch a guest profile by email address."""

    @abstractmethod
    async def search_guests(
        self,
        query: str,
        limit: int = 20,
    ) -> list[PMSGuest]:
        """Full-text search across name, email, loyalty number."""

    # ── Reservation operations ───────────────────────────────────────────────

    @abstractmethod
    async def get_reservation(self, reservation_id: str) -> Reservation:
        """Fetch a single reservation by ID."""

    @abstractmethod
    async def get_reservations_for_guest(
        self,
        guest_id: str,
        limit: int = 10,
    ) -> list[Reservation]:
        """Return recent reservations for a guest."""

    # ── Room / housekeeping operations ───────────────────────────────────────

    @abstractmethod
    async def get_room(self, room_number: str, property_id: str) -> Room:
        """Fetch current status of a specific room."""

    @abstractmethod
    async def list_rooms(
        self,
        property_id: str,
        floor: str | None = None,
        room_type: str | None = None,
        limit: int = 100,
    ) -> list[Room]:
        """List rooms, optionally filtered by floor or type."""
