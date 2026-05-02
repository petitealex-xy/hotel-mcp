"""In-memory mock CRM adapter for local dev and tests."""

from __future__ import annotations

from datetime import date

from src.adapters.crm.base import BaseCRMAdapter
from src.adapters.pms.base import GuestNotFound
from src.models.guest import CRMGuest, Gender, GuestPreferences, LoyaltyTier

_CONTACTS: dict[str, CRMGuest] = {
    "CRM-001": CRMGuest(
        crm_id="CRM-001",
        first_name="Marie",
        last_name="Dupont",
        email="marie.dupont@example.com",
        phone="+33612345678",
        date_of_birth=date(1985, 6, 15),
        gender=Gender.FEMALE,
        preferred_language="fr",
        loyalty_number="LYL-99001",
        loyalty_tier=LoyaltyTier.GOLD,
        segment="leisure",
        preferences=GuestPreferences(
            room_type="king",
            floor_preference="high",
            dietary_restrictions=["vegetarian"],
            languages=["fr", "en"],
            special_occasions=["anniversary"],
        ),
        gdpr_consent=True,
        gdpr_consent_date=date(2022, 5, 10),
        marketing_opt_in=True,
        source_system="mock_crm",
    ),
    "CRM-002": CRMGuest(
        crm_id="CRM-002",
        first_name="James",
        last_name="O'Brien",
        email="james.obrien@corporate.ie",
        phone="+35312345678",
        preferred_language="en",
        loyalty_number="LYL-99002",
        loyalty_tier=LoyaltyTier.SILVER,
        segment="business",
        preferences=GuestPreferences(
            room_type="twin",
            floor_preference="quiet",
        ),
        gdpr_consent=True,
        gdpr_consent_date=date(2023, 1, 15),
        source_system="mock_crm",
    ),
    "CRM-003": CRMGuest(
        # Deliberate mismatches vs PMS-003 for reconciliation demos
        crm_id="CRM-003",
        first_name="Yuki",
        last_name="Tanaka",
        email="yuki.tanaka@tanaka-group.jp",   # different from PMS
        phone="+81901234567",
        preferred_language="ja",
        loyalty_number="LYL-99003",
        loyalty_tier=LoyaltyTier.GOLD,         # PMS says PLATINUM — conflict
        segment="business",
        preferences=GuestPreferences(
            room_type="suite",
            dietary_restrictions=["no pork"],
            languages=["ja", "en"],
        ),
        gdpr_consent=True,
        source_system="mock_crm",
    ),
}


class MockCRMAdapter(BaseCRMAdapter):
    async def health_check(self) -> dict[str, str]:
        return {"status": "ok", "system": "mock_crm"}

    async def get_contact_by_id(self, contact_id: str) -> CRMGuest:
        if contact_id not in _CONTACTS:
            raise GuestNotFound(f"Mock CRM: contact {contact_id!r} not found")
        return _CONTACTS[contact_id]

    async def get_contact_by_email(self, email: str) -> CRMGuest:
        for c in _CONTACTS.values():
            if c.email and c.email.lower() == email.lower():
                return c
        raise GuestNotFound(f"Mock CRM: no contact with email {email!r}")

    async def get_contact_by_loyalty_number(self, loyalty_number: str) -> CRMGuest:
        for c in _CONTACTS.values():
            if c.loyalty_number == loyalty_number:
                return c
        raise GuestNotFound(f"Mock CRM: no contact with loyalty number {loyalty_number!r}")

    async def search_contacts(self, query: str, limit: int = 20) -> list[CRMGuest]:
        q = query.lower()
        results = [
            c for c in _CONTACTS.values()
            if q in c.first_name.lower()
            or q in c.last_name.lower()
            or (c.email and q in c.email.lower())
        ]
        return results[:limit]
