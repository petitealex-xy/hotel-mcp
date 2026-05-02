"""MCP tool: reservation retrieval."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from src.adapters import get_pms_adapter
from src.adapters.pms.base import ReservationNotFound
from src.utils.audit import audit_tool_call

logger = structlog.get_logger(__name__)

_pms = get_pms_adapter()


def register_reservation_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="get_reservation",
        description=(
            "Fetch full reservation details from the PMS by reservation ID. "
            "Returns arrival/departure dates, room assignment, rate details, "
            "special requests, and current status. Read-only."
        ),
    )
    async def get_reservation(
        reservation_id: str,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["reservation_id"],
          "properties": {
            "reservation_id": {"type": "string"},
            "caller_id":      {"type": "string"}
          }
        }
        """
        args = {"reservation_id": reservation_id}
        async with audit_tool_call("get_reservation", args, caller_id):
            try:
                res = await _pms.get_reservation(reservation_id)
            except ReservationNotFound as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                logger.error("get_reservation_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        return {
            "source": "pms",
            "reservation": res.model_dump(mode="json"),
        }

    @mcp.tool(
        name="get_reservations_for_guest",
        description=(
            "Return recent reservations for a guest from the PMS. "
            "Useful for understanding stay history and patterns. Read-only."
        ),
    )
    async def get_reservations_for_guest(
        pms_guest_id: str,
        limit: int = 10,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["pms_guest_id"],
          "properties": {
            "pms_guest_id": {"type": "string"},
            "limit":        {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "caller_id":    {"type": "string"}
          }
        }
        """
        limit = max(1, min(50, limit))
        args = {"pms_guest_id": pms_guest_id, "limit": limit}
        async with audit_tool_call("get_reservations_for_guest", args, caller_id):
            try:
                reservations = await _pms.get_reservations_for_guest(pms_guest_id, limit=limit)
            except Exception as exc:
                logger.error("get_reservations_for_guest_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        return {
            "source": "pms",
            "pms_guest_id": pms_guest_id,
            "count": len(reservations),
            "reservations": [r.model_dump(mode="json") for r in reservations],
        }
