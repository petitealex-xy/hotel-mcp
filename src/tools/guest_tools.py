"""
MCP tools: guest-profile retrieval from PMS and CRM.

Each tool function is a plain async function registered on the FastMCP
instance in server.py. Adapters are instantiated once at module load and
reused across calls (connection pooling inside httpx.AsyncClient).
"""

from __future__ import annotations

import logging

import structlog
from mcp.server.fastmcp import FastMCP

from src.adapters import get_crm_adapter, get_pms_adapter
from src.adapters.pms.base import GuestNotFound
from src.models.guest import CRMGuest, PMSGuest
from src.utils.audit import audit_tool_call

logger = structlog.get_logger(__name__)

_pms = get_pms_adapter()
_crm = get_crm_adapter()


def register_guest_tools(mcp: FastMCP) -> None:
    """Attach all guest-profile tools to the MCP server."""

    # ── get_guest_from_pms ───────────────────────────────────────────────────

    @mcp.tool(
        name="get_guest_from_pms",
        description=(
            "Retrieve a guest profile from the Property Management System (PMS). "
            "Provide either guest_id (native PMS identifier) or email. "
            "Returns name, contact details, loyalty status, and stay history. "
            "Read-only. No data is modified."
        ),
    )
    async def get_guest_from_pms(
        guest_id: str | None = None,
        email: str | None = None,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema (JSON Schema):
        {
          "type": "object",
          "properties": {
            "guest_id": {"type": "string", "description": "PMS native guest identifier"},
            "email":    {"type": "string", "format": "email"},
            "caller_id":{"type": "string", "description": "Staff ID or token subject for audit"}
          },
          "oneOf": [
            {"required": ["guest_id"]},
            {"required": ["email"]}
          ]
        }
        """
        if not guest_id and not email:
            return {
                "error": "validation_error",
                "message": "Provide either guest_id or email.",
            }

        args = {"guest_id": guest_id, "email": email}
        async with audit_tool_call("get_guest_from_pms", args, caller_id):
            try:
                if guest_id:
                    guest = await _pms.get_guest_by_id(guest_id)
                else:
                    guest = await _pms.get_guest_by_email(email)  # type: ignore[arg-type]
            except GuestNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                logger.error("get_guest_from_pms_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        return {
            "source": "pms",
            "guest": guest.model_dump(mode="json"),
        }

    # ── get_guest_from_crm ───────────────────────────────────────────────────

    @mcp.tool(
        name="get_guest_from_crm",
        description=(
            "Retrieve a guest (contact) profile from the CRM. "
            "Provide crm_id, email, or loyalty_number. "
            "Returns contact details, preferences, loyalty info, and GDPR consent status. "
            "Read-only."
        ),
    )
    async def get_guest_from_crm(
        crm_id: str | None = None,
        email: str | None = None,
        loyalty_number: str | None = None,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "properties": {
            "crm_id":         {"type": "string"},
            "email":          {"type": "string", "format": "email"},
            "loyalty_number": {"type": "string"},
            "caller_id":      {"type": "string"}
          },
          "oneOf": [
            {"required": ["crm_id"]},
            {"required": ["email"]},
            {"required": ["loyalty_number"]}
          ]
        }
        """
        if not any([crm_id, email, loyalty_number]):
            return {
                "error": "validation_error",
                "message": "Provide at least one of: crm_id, email, loyalty_number.",
            }

        args = {"crm_id": crm_id, "email": email, "loyalty_number": loyalty_number}
        async with audit_tool_call("get_guest_from_crm", args, caller_id):
            try:
                if crm_id:
                    guest = await _crm.get_contact_by_id(crm_id)
                elif email:
                    guest = await _crm.get_contact_by_email(email)
                else:
                    guest = await _crm.get_contact_by_loyalty_number(loyalty_number)  # type: ignore[arg-type]
            except GuestNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                logger.error("get_guest_from_crm_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        return {
            "source": "crm",
            "guest": guest.model_dump(mode="json"),
        }

    # ── compare_guest_records ────────────────────────────────────────────────

    @mcp.tool(
        name="compare_guest_records",
        description=(
            "Compare a guest's records from PMS and CRM side-by-side. "
            "Returns a list of field-level differences with severity ratings, "
            "recommended authoritative source for each field, and a confidence score. "
            "Read-only — no changes are made. Use suggest_sync_actions to get "
            "a full reconciliation plan."
        ),
    )
    async def compare_guest_records(
        pms_id: str,
        crm_id: str,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["pms_id", "crm_id"],
          "properties": {
            "pms_id":    {"type": "string"},
            "crm_id":    {"type": "string"},
            "caller_id": {"type": "string"}
          }
        }
        """
        from src.utils.reconcile import compare_records

        args = {"pms_id": pms_id, "crm_id": crm_id}
        async with audit_tool_call("compare_guest_records", args, caller_id):
            try:
                pms_guest = await _pms.get_guest_by_id(pms_id)
                crm_guest = await _crm.get_contact_by_id(crm_id)
            except GuestNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                return {"error": "upstream_error", "message": str(exc)}

            diffs = compare_records(pms_guest, crm_guest)

        return {
            "pms_id": pms_id,
            "crm_id": crm_id,
            "total_differences": len(diffs),
            "conflicts": sum(1 for d in diffs if d.severity == "conflict"),
            "warnings": sum(1 for d in diffs if d.severity == "warning"),
            "diffs": [d.model_dump(mode="json") for d in diffs],
        }

    # ── generate_guest_unified_view ──────────────────────────────────────────

    @mcp.tool(
        name="generate_guest_unified_view",
        description=(
            "Produce a single, reconciled guest profile merging data from PMS and CRM. "
            "PMS data is authoritative for transactional fields (stays, loyalty tier, revenue). "
            "CRM data is authoritative for preferences and GDPR consent. "
            "Includes a confidence score and data-quality flags. Read-only."
        ),
    )
    async def generate_guest_unified_view(
        pms_id: str,
        crm_id: str,
        caller_id: str = "anonymous",
    ) -> dict:
        from src.utils.reconcile import build_unified_view

        args = {"pms_id": pms_id, "crm_id": crm_id}
        async with audit_tool_call("generate_guest_unified_view", args, caller_id):
            try:
                pms_guest = await _pms.get_guest_by_id(pms_id)
                crm_guest = await _crm.get_contact_by_id(crm_id)
            except GuestNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                return {"error": "upstream_error", "message": str(exc)}

            unified = build_unified_view(pms_guest, crm_guest)

        return {
            "unified_guest": unified.model_dump(mode="json"),
            "data_quality": {
                "confidence_score": unified.confidence_score,
                "flags": [f.value for f in unified.quality_flags],
                "missing_fields": unified.missing_fields,
                "notes": unified.reconciliation_notes,
            },
        }
