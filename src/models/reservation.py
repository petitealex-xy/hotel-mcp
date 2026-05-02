"""Reservation data model — PMS-sourced."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class ReservationStatus(StrEnum):
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    WAITLIST = "waitlist"


class RateType(StrEnum):
    BAR = "bar"             # Best available rate
    CORPORATE = "corporate"
    PACKAGE = "package"
    LOYALTY = "loyalty"
    OTA = "ota"
    NEGOTIATED = "negotiated"
    COMPLEMENTARY = "complementary"


class GuestCount(BaseModel):
    adults: Annotated[int, Field(ge=0)] = 1
    children: Annotated[int, Field(ge=0)] = 0
    infants: Annotated[int, Field(ge=0)] = 0


class RateDetail(BaseModel):
    rate_code: str
    rate_type: RateType
    daily_rate: Annotated[float, Field(ge=0)]
    currency: str = "EUR"
    includes_breakfast: bool = False
    is_non_refundable: bool = False


class SpecialRequest(BaseModel):
    category: str  # e.g. "accessibility", "celebration", "dietary"
    description: str
    fulfilled: bool = False


class Reservation(BaseModel):
    """
    Full reservation record as returned by the PMS adapter.
    All monetary amounts are in the property's billing currency unless noted.
    """

    reservation_id: str
    confirmation_number: str  # guest-facing code
    property_id: str

    # Guest linkage
    pms_guest_id: str
    guest_name: str           # denormalised for display without a join

    # Dates
    arrival_date: date
    departure_date: date
    actual_check_in: datetime | None = None
    actual_check_out: datetime | None = None

    # Room assignment
    room_number: str | None = None
    room_type_booked: str
    room_type_assigned: str | None = None

    # Party
    guest_count: GuestCount = Field(default_factory=GuestCount)

    # Financials
    rate: RateDetail
    total_charges: Annotated[float, Field(ge=0)] = 0.0
    total_paid: Annotated[float, Field(ge=0)] = 0.0
    balance_due: float = 0.0
    currency: str = "EUR"

    # Status & channel
    status: ReservationStatus = ReservationStatus.CONFIRMED
    booking_channel: str | None = None   # "direct", "booking.com", "expedia", …
    booking_date: date | None = None
    cancellation_policy: str | None = None

    # Service flags
    special_requests: list[SpecialRequest] = Field(default_factory=list)
    notes: str | None = None
    is_vip: bool = False
    upgrade_eligible: bool = False

    source_system: str = "pms"
