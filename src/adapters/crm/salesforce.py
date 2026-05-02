"""
Salesforce CRM adapter.

Uses Salesforce REST API v59+ with OAuth 2.0 Connected App credentials.
Maps Salesforce Contact / Account objects to our CRMGuest model.

Rate limits: Salesforce imposes per-org API request limits (typically
15,000–100,000 req/24h depending on licence). We track usage via the
Sforce-Limit-Info response header and surface it in structured logs.
"""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.adapters.crm.base import BaseCRMAdapter
from src.adapters.pms.base import GuestNotFound, RateLimitExceeded, UpstreamUnavailable
from src.config import CRMConfig
from src.models.guest import CRMGuest, Gender, GuestPreferences, LoyaltyTier

logger = logging.getLogger(__name__)


class SalesforceAdapter(BaseCRMAdapter):
    """
    Salesforce CRM connector.

    Assumes a custom object `Hotel_Loyalty__c` linked to the Contact
    for loyalty data, and a `Hotel_Preferences__c` object for preferences.
    Adjust SOQL queries to match your Salesforce org's schema.
    """

    _CONTACT_FIELDS = (
        "Id, FirstName, LastName, Email, Phone, Birthdate, "
        "MailingCountryCode, Gender__c, PreferredLanguage__c, "
        "HasOptedOutOfEmail, GDPR_Consent__c, GDPR_Consent_Date__c, "
        "Segment__c, "
        "(SELECT MembershipId__c, TierCode__c FROM Hotel_Loyalty__r LIMIT 1), "
        "(SELECT RoomType__c, FloorPref__c, DietaryRestrictions__c, Languages__c "
        " FROM Hotel_Preferences__r LIMIT 1)"
    )

    def __init__(self, config: CRMConfig) -> None:
        self._config = config
        self._access_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.instance_url or self._config.base_url,
                timeout=self._config.timeout_seconds,
            )
        return self._client

    async def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        client = await self._get_client()
        try:
            resp = await client.post(
                "https://login.salesforce.com/services/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.api_key,
                    "client_secret": "",  # from secret manager
                },
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            return self._access_token
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Salesforce auth failed: {exc}") from exc

    async def _soql(self, query: str) -> list[dict]:
        client = await self._get_client()
        token = await self._get_token()
        try:
            resp = await client.get(
                "/services/data/v59.0/query",
                params={"q": query},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.ConnectError as exc:
            raise UpstreamUnavailable(f"Cannot reach Salesforce: {exc}") from exc

        if resp.status_code == 429:
            raise RateLimitExceeded("Salesforce API limit reached")
        if resp.status_code >= 500:
            raise UpstreamUnavailable(f"Salesforce 5xx: {resp.status_code}")

        # Surface remaining API call budget to structured logs
        limit_info = resp.headers.get("Sforce-Limit-Info", "")
        if limit_info:
            logger.debug("salesforce_api_budget", extra={"limit_info": limit_info})

        resp.raise_for_status()
        return resp.json().get("records", [])

    def _parse_contact(self, record: dict) -> CRMGuest:
        loyalty = (record.get("Hotel_Loyalty__r") or {}).get("records", [{}])
        loyalty = loyalty[0] if loyalty else {}
        prefs_raw = (record.get("Hotel_Preferences__r") or {}).get("records", [{}])
        prefs_raw = prefs_raw[0] if prefs_raw else {}

        tier_map = {"Silver": LoyaltyTier.SILVER, "Gold": LoyaltyTier.GOLD, "Platinum": LoyaltyTier.PLATINUM}

        prefs = GuestPreferences(
            room_type=prefs_raw.get("RoomType__c"),
            floor_preference=prefs_raw.get("FloorPref__c"),
            dietary_restrictions=[
                d.strip() for d in (prefs_raw.get("DietaryRestrictions__c") or "").split(";") if d.strip()
            ],
            languages=[
                l.strip() for l in (prefs_raw.get("Languages__c") or "").split(";") if l.strip()
            ],
        )

        return CRMGuest(
            crm_id=record["Id"],
            first_name=record.get("FirstName") or "",
            last_name=record.get("LastName") or "",
            email=record.get("Email"),
            phone=record.get("Phone"),
            date_of_birth=record.get("Birthdate"),
            gender={"Male": Gender.MALE, "Female": Gender.FEMALE}.get(
                record.get("Gender__c") or "", Gender.UNKNOWN
            ),
            preferred_language=record.get("PreferredLanguage__c") or "en",
            loyalty_number=loyalty.get("MembershipId__c"),
            loyalty_tier=tier_map.get(loyalty.get("TierCode__c") or "", LoyaltyTier.NONE),
            segment=record.get("Segment__c"),
            preferences=prefs,
            gdpr_consent=bool(record.get("GDPR_Consent__c")),
            gdpr_consent_date=record.get("GDPR_Consent_Date__c"),
            marketing_opt_in=not bool(record.get("HasOptedOutOfEmail")),
            source_system="salesforce",
        )

    async def health_check(self) -> dict[str, str]:
        try:
            records = await self._soql("SELECT Id FROM Contact LIMIT 1")
            return {"status": "ok", "system": "salesforce"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    @retry(
        retry=retry_if_exception_type(UpstreamUnavailable),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_contact_by_id(self, contact_id: str) -> CRMGuest:
        records = await self._soql(
            f"SELECT {self._CONTACT_FIELDS} FROM Contact WHERE Id = '{contact_id}' LIMIT 1"
        )
        if not records:
            raise GuestNotFound(f"Salesforce: contact {contact_id!r} not found")
        return self._parse_contact(records[0])

    async def get_contact_by_email(self, email: str) -> CRMGuest:
        safe_email = email.replace("'", "\\'")
        records = await self._soql(
            f"SELECT {self._CONTACT_FIELDS} FROM Contact WHERE Email = '{safe_email}' LIMIT 1"
        )
        if not records:
            raise GuestNotFound(f"Salesforce: no contact with email {email!r}")
        return self._parse_contact(records[0])

    async def get_contact_by_loyalty_number(self, loyalty_number: str) -> CRMGuest:
        safe = loyalty_number.replace("'", "\\'")
        records = await self._soql(
            f"SELECT {self._CONTACT_FIELDS} FROM Contact "
            f"WHERE Id IN (SELECT Contact__c FROM Hotel_Loyalty__c "
            f"WHERE MembershipId__c = '{safe}') LIMIT 1"
        )
        if not records:
            raise GuestNotFound(f"Salesforce: no contact with loyalty number {loyalty_number!r}")
        return self._parse_contact(records[0])

    async def search_contacts(self, query: str, limit: int = 20) -> list[CRMGuest]:
        safe = query.replace("'", "\\'")
        records = await self._soql(
            f"SELECT {self._CONTACT_FIELDS} FROM Contact "
            f"WHERE Name LIKE '%{safe}%' OR Email LIKE '%{safe}%' "
            f"LIMIT {limit}"
        )
        return [self._parse_contact(r) for r in records]
