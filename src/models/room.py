"""Room and housekeeping status models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RoomStatus(StrEnum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    OUT_OF_ORDER = "out_of_order"
    OUT_OF_SERVICE = "out_of_service"


class HousekeepingStatus(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"
    INSPECTED = "inspected"
    IN_PROGRESS = "in_progress"
    TOUCH_UP = "touch_up"
    DO_NOT_DISTURB = "do_not_disturb"
    REFUSED = "refused"


class MaintenanceFlag(BaseModel):
    issue_code: str
    description: str
    reported_at: datetime
    priority: str  # "low" | "medium" | "high" | "urgent"
    resolved: bool = False


class Room(BaseModel):
    """
    Current operational state of a hotel room.
    Combining PMS occupancy data with housekeeping task status.
    """

    room_number: str
    property_id: str
    floor: str | None = None
    room_type: str
    room_type_label: str | None = None   # human-readable, potentially localised

    # Occupancy
    room_status: RoomStatus = RoomStatus.VACANT
    reservation_id: str | None = None    # set when occupied
    guest_name: str | None = None        # denormalised for front-desk use
    expected_departure: str | None = None

    # Housekeeping
    housekeeping_status: HousekeepingStatus = HousekeepingStatus.DIRTY
    last_cleaned_at: datetime | None = None
    assigned_attendant: str | None = None
    priority_clean: bool = False         # e.g. VIP arrival, early check-in request

    # Maintenance
    maintenance_flags: list[MaintenanceFlag] = Field(default_factory=list)
    is_blocked: bool = False
    block_reason: str | None = None

    # Amenities & config
    bed_configuration: str | None = None
    max_occupancy: int = 2
    connecting_room: str | None = None
    smoking: bool = False
    accessible: bool = False

    source_system: str = "pms"
    last_updated_at: datetime | None = None
