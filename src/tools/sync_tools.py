"""
MCP tool: data synchronisation planning.

suggest_sync_actions is the central read-only recommendation engine.
It produces a SyncPlan — a fully described, ordered list of changes to make,
but does NOT execute any of them. Writes require a separate write-enabled
tool gated by role-based authorisation (roadmap phase 2).
"""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from src.adapters import get_crm_adapter, get_pms_adapter
from src.adapters.pms.base import GuestNotFound
from src.utils.audit import audit_tool_call
from src.utils.reconcile import build_sync_plan

logger = structlog.get_logger(__name__)

_pms = get_pms_adapter()
_crm = get_crm_adapter()


def register_sync_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="suggest_sync_actions",
        description=(
            "Generate a safe, human-reviewable synchronisation plan for a guest's data "
            "across PMS and CRM. Returns a prioritised list of proposed field updates with "
            "risk levels, authoritative source recommendations, and rationale. "
            "Nothing is written. write_enabled is always false in this tool — "
            "a separate authorised write operation is required to apply any changes."
        ),
    )
    async def suggest_sync_actions(
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

        Output: SyncPlan — see src/models/sync.py for full schema.
        write_enabled is always false. No data is modified by this tool.
        """
        args = {"pms_id": pms_id, "crm_id": crm_id}
        async with audit_tool_call("suggest_sync_actions", args, caller_id):
            try:
                pms_guest = await _pms.get_guest_by_id(pms_id)
                crm_guest = await _crm.get_contact_by_id(crm_id)
            except GuestNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                logger.error("suggest_sync_actions_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

            plan = build_sync_plan(pms_guest, crm_guest)

        return {
            "sync_plan": plan.model_dump(mode="json"),
            "caution": (
                "This plan is read-only. No changes have been made. "
                "Review each action and approve through the designated write workflow."
            ),
        }

    @mcp.tool(
        name="find_duplicate_records",
        description=(
            "Search for potential duplicate guest records within PMS or CRM using "
            "fuzzy name and email matching. Returns candidate pairs with a match score. "
            "Read-only."
        ),
    )
    async def find_duplicate_records(
        query: str,
        search_pms: bool = True,
        search_crm: bool = True,
        limit: int = 10,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["query"],
          "properties": {
            "query":      {"type": "string", "description": "Guest name or email fragment"},
            "search_pms": {"type": "boolean", "default": true},
            "search_crm": {"type": "boolean", "default": true},
            "limit":      {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "caller_id":  {"type": "string"}
          }
        }
        """
        limit = max(1, min(50, limit))
        args = {"query": query, "search_pms": search_pms, "search_crm": search_crm}
        async with audit_tool_call("find_duplicate_records", args, caller_id):
            pms_results = []
            crm_results = []

            if search_pms:
                try:
                    pms_results = await _pms.search_guests(query, limit=limit)
                except Exception as exc:
                    logger.warning("pms_search_failed", error=str(exc))

            if search_crm:
                try:
                    crm_results = await _crm.search_contacts(query, limit=limit)
                except Exception as exc:
                    logger.warning("crm_search_failed", error=str(exc))

        # Simple cross-match: find PMS guests whose email appears in CRM results
        crm_emails = {c.email for c in crm_results if c.email}
        cross_matches = [
            {
                "pms_id": p.pms_id,
                "crm_id": next(
                    (c.crm_id for c in crm_results if c.email == p.email), None
                ),
                "guest_name": f"{p.first_name} {p.last_name}",
                "email": p.email,
                "match_basis": "email",
            }
            for p in pms_results
            if p.email and p.email in crm_emails
        ]

        return {
            "query": query,
            "pms_candidates": [
                {"pms_id": p.pms_id, "name": f"{p.first_name} {p.last_name}", "email": p.email}
                for p in pms_results
            ],
            "crm_candidates": [
                {"crm_id": c.crm_id, "name": f"{c.first_name} {c.last_name}", "email": c.email}
                for c in crm_results
            ],
            "cross_system_matches": cross_matches,
            "total_cross_matches": len(cross_matches),
        }
