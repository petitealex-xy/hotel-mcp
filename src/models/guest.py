"""
Guest data models.

Three layers:
  PMSGuest    — raw shape coming from the Property Management System
  CRMGuest    — raw shape coming from the CRM
  UnifiedGuestView — reconciled, canonical representation used by tools
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"
    UNKNOWN = "unknown"


class LoyaltyTier(StrEnum):
    NONE = "none"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class GuestPreferences(BaseModel):
    """Lifestyle and service preferences — CRM-sourced, curated by staff."""

    room_type: str | None = None          # e.g. "king", "twin", "suite"
    floor_preference: str | None = None   # "high", "low", "quiet"
    pillow_type: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)  # ISO 639-1 codes
    special_occasions: list[str] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)
    notes: str | None = None


class PMSGuest(BaseModel):
    """
    Canonical shape for data fetched from a Property Management System.
    Field names match the MCP tool output contract — adapters must normalise
    to this shape before returning.
    """

    pms_id: str = Field(..., description="Native PMS guest record identifier")
    property_id: str
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender = Gender.UNKNOWN
    nationality: str | None = None        # ISO 3166-1 alpha-2
    passport_number: str | None = None
    vip_code: str | None = None
    loyalty_number: str | None = None
    loyalty_tier: LoyaltyTier = LoyaltyTier.NONE
    total_stays: int = 0
    total_revenue: float = 0.0
    currency: str = "EUR"
    last_stay_date: date | None = None
    source_system: str = "pms"
    raw_source_version: str | None = None  # adapter schema version

    @field_validator("nationality", mode="before")
    @classmethod
    def upper_iso(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class CRMGuest(BaseModel):
    """
    Canonical shape for data fetched from a CRM.
    """

    crm_id: str = Field(..., description="Native CRM contact identifier")
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender = Gender.UNKNOWN
    preferred_language: str = "en"         # ISO 639-1
    loyalty_number: str | None = None
    loyalty_tier: LoyaltyTier = LoyaltyTier.NONE
    segment: str | None = None             # e.g. "business", "leisure", "group"
    preferences: GuestPreferences = Field(default_factory=GuestPreferences)
    gdpr_consent: bool = False
    gdpr_consent_date: date | None = None
    marketing_opt_in: bool = False
    source_system: str = "crm"
    raw_source_version: str | None = None


# Fields that are compared during reconciliation and their human labels.
# Order matters: higher-priority fields first.
RECONCILABLE_FIELDS: list[tuple[str, str]] = [
    ("email", "Email address"),
    ("phone", "Phone number"),
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("date_of_birth", "Date of birth"),
    ("gender", "Gender"),
    ("loyalty_number", "Loyalty number"),
    ("loyalty_tier", "Loyalty tier"),
    ("nationality", "Nationality"),
]


class DataQualityFlag(StrEnum):
    MISSING_EMAIL = "missing_email"
    MISSING_PHONE = "missing_phone"
    MISSING_DOB = "missing_dob"
    MISSING_NATIONALITY = "missing_nationality"
    MISSING_GDPR_CONSENT = "missing_gdpr_consent"
    LOYALTY_TIER_MISMATCH = "loyalty_tier_mismatch"
    NAME_MISMATCH = "name_mismatch"
    EMAIL_MISMATCH = "email_mismatch"


class UnifiedGuestView(BaseModel):
    """
    Reconciled, read-only snapshot of a guest across PMS and CRM.
    This is what AI assistants and staff-facing tools consume.
    """

    # Canonical identity
    pms_id: str | None = None
    crm_id: str | None = None
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender = Gender.UNKNOWN
    nationality: str | None = None
    preferred_language: str = "en"

    # Loyalty & segmentation
    loyalty_number: str | None = None
    loyalty_tier: LoyaltyTier = LoyaltyTier.NONE
    segment: str | None = None

    # Stay history (PMS-sourced)
    total_stays: int = 0
    total_revenue: Annotated[float, Field(ge=0)] = 0.0
    currency: str = "EUR"
    last_stay_date: date | None = None

    # Preferences (CRM-sourced)
    preferences: GuestPreferences = Field(default_factory=GuestPreferences)

    # Privacy
    gdpr_consent: bool = False
    marketing_opt_in: bool = False

    # Data-quality signals
    quality_flags: list[DataQualityFlag] = Field(default_factory=list)
    confidence_score: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    missing_fields: list[str] = Field(default_factory=list)
    reconciliation_notes: list[str] = Field(default_factory=list)
