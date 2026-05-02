"""
MCP resources — static and semi-static context documents.

Resources are NOT tools. They expose read-only context that the MCP client
can fetch to ground the AI assistant's understanding of the hotel environment.
Think of them as a knowledge base the assistant can query before acting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from src.adapters import get_crm_adapter, get_pms_adapter
from src.config import settings


def register_resources(mcp: FastMCP) -> None:

    @mcp.resource("hotel://server/info")
    async def server_info() -> str:
        """Server metadata, active adapters, and environment."""
        return json.dumps(
            {
                "server_name": settings.server.server_name,
                "environment": settings.server.env,
                "pms_adapter": settings.pms.adapter,
                "crm_adapter": settings.crm.adapter,
                "auth_required": settings.auth.require_auth,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )

    @mcp.resource("hotel://server/health")
    async def health() -> str:
        """Live health check for both upstream adapters."""
        pms = get_pms_adapter()
        crm = get_crm_adapter()
        pms_health = await pms.health_check()
        crm_health = await crm.health_check()
        return json.dumps(
            {
                "pms": pms_health,
                "crm": crm_health,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )

    @mcp.resource("hotel://schema/guest-fields")
    async def guest_fields() -> str:
        """
        Canonical list of guest fields, their sources, and privacy classification.
        Useful for AI assistants deciding which fields to request or display.
        """
        fields = [
            {"field": "first_name",       "source": "pms+crm", "pii": True,  "gdpr_basis": "contract"},
            {"field": "last_name",        "source": "pms+crm", "pii": True,  "gdpr_basis": "contract"},
            {"field": "email",            "source": "pms+crm", "pii": True,  "gdpr_basis": "contract"},
            {"field": "phone",            "source": "pms+crm", "pii": True,  "gdpr_basis": "contract"},
            {"field": "date_of_birth",    "source": "pms",     "pii": True,  "gdpr_basis": "contract"},
            {"field": "nationality",      "source": "pms",     "pii": True,  "gdpr_basis": "contract"},
            {"field": "passport_number",  "source": "pms",     "pii": True,  "gdpr_basis": "legal_obligation", "sensitivity": "high"},
            {"field": "loyalty_number",   "source": "pms+crm", "pii": False, "gdpr_basis": "contract"},
            {"field": "loyalty_tier",     "source": "pms",     "pii": False, "gdpr_basis": "contract"},
            {"field": "total_stays",      "source": "pms",     "pii": False, "gdpr_basis": "legitimate_interest"},
            {"field": "total_revenue",    "source": "pms",     "pii": False, "gdpr_basis": "legitimate_interest", "display_restriction": "management_only"},
            {"field": "preferences",      "source": "crm",     "pii": True,  "gdpr_basis": "consent"},
            {"field": "gdpr_consent",     "source": "crm",     "pii": False, "gdpr_basis": "n/a"},
            {"field": "marketing_opt_in", "source": "crm",     "pii": False, "gdpr_basis": "consent"},
        ]
        return json.dumps({"guest_fields": fields}, indent=2)

    @mcp.resource("hotel://schema/room-status-codes")
    async def room_status_codes() -> str:
        """Reference table for room status and housekeeping codes."""
        return json.dumps(
            {
                "room_status": {
                    "vacant":           "Room is unoccupied and available",
                    "occupied":         "Guest is currently checked in",
                    "out_of_order":     "Room cannot be sold — maintenance required",
                    "out_of_service":   "Temporarily unavailable but can be sold if needed",
                },
                "housekeeping_status": {
                    "clean":            "Room cleaned but not yet inspected",
                    "dirty":            "Awaiting cleaning",
                    "inspected":        "Cleaned and passed supervisor inspection — ready to sell",
                    "in_progress":      "Attendant currently cleaning",
                    "touch_up":         "Minor tidying required",
                    "do_not_disturb":   "Guest has set DND — do not enter",
                    "refused":          "Guest refused service today",
                },
            },
            indent=2,
        )

    @mcp.resource("hotel://policy/data-handling")
    async def data_handling_policy() -> str:
        """
        Data handling policy summary for AI assistants.
        Assistants must follow these rules when presenting guest data.
        """
        return """
# Hotel MCP — Data Handling Policy (AI Assistant Guidelines)

## General principles
- Guest data is confidential. Never display it to unauthorised callers.
- Prefer showing aggregated/anonymised data where a specific record is not needed.
- Always surface the `gdpr_consent` field when presenting marketing-related data.
- Do not suggest actions that would store guest data in external services not listed here.

## Field sensitivity
- `passport_number`, `date_of_birth` — high sensitivity. Only display to front-desk and management roles.
- `total_revenue`, `total_stays` — internal only. Do not share with guests directly.
- `email`, `phone` — mask in logs. Confirm identity before sharing.

## Write actions
- All write tools require explicit approval from an authorised staff member.
- Never propose writes that remove GDPR consent or marketing opt-in without a guest request.
- Sync actions that affect `email` always require manual review regardless of role.

## Data residency
- This deployment is configured for EU data residency.
- Do not suggest exporting guest data to systems outside the EU without a DPA.

## Retention
- Guest data is retained for 3 years post last-stay for transactional records.
- Preference data without a recent stay is deleted after 2 years.
- Anonymisation pipeline runs quarterly.
"""
