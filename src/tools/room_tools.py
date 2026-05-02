"""MCP tool: room and housekeeping status."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from src.adapters import get_pms_adapter
from src.adapters.pms.base import AdapterError
from src.utils.audit import audit_tool_call

logger = structlog.get_logger(__name__)

_pms = get_pms_adapter()


def register_room_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="get_room_status",
        description=(
            "Fetch the current occupancy and housekeeping status for a specific room. "
            "Returns room type, occupancy state, housekeeping status, assigned attendant, "
            "and any active maintenance flags. Read-only."
        ),
    )
    async def get_room_status(
        room_number: str,
        property_id: str,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["room_number", "property_id"],
          "properties": {
            "room_number": {"type": "string"},
            "property_id": {"type": "string"},
            "caller_id":   {"type": "string"}
          }
        }
        """
        args = {"room_number": room_number, "property_id": property_id}
        async with audit_tool_call("get_room_status", args, caller_id):
            try:
                room = await _pms.get_room(room_number, property_id)
            except AdapterError as exc:
                return {"error": "not_found", "message": str(exc)}
            except Exception as exc:
                logger.error("get_room_status_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        return {
            "source": "pms",
            "room": room.model_dump(mode="json"),
            "summary": {
                "room_number": room.room_number,
                "occupancy": room.room_status.value,
                "housekeeping": room.housekeeping_status.value,
                "priority_clean": room.priority_clean,
                "maintenance_issues": len(room.maintenance_flags),
                "is_blocked": room.is_blocked,
            },
        }

    @mcp.tool(
        name="list_rooms",
        description=(
            "List rooms in a property with their current occupancy and housekeeping status. "
            "Supports filtering by floor or room type. Read-only."
        ),
    )
    async def list_rooms(
        property_id: str,
        floor: str | None = None,
        room_type: str | None = None,
        limit: int = 50,
        caller_id: str = "anonymous",
    ) -> dict:
        """
        Input schema:
        {
          "type": "object",
          "required": ["property_id"],
          "properties": {
            "property_id": {"type": "string"},
            "floor":       {"type": "string", "description": "Filter by floor number"},
            "room_type":   {"type": "string", "description": "Filter by room type code"},
            "limit":       {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            "caller_id":   {"type": "string"}
          }
        }
        """
        limit = max(1, min(200, limit))
        args = {"property_id": property_id, "floor": floor, "room_type": room_type, "limit": limit}
        async with audit_tool_call("list_rooms", args, caller_id):
            try:
                rooms = await _pms.list_rooms(property_id, floor=floor, room_type=room_type, limit=limit)
            except Exception as exc:
                logger.error("list_rooms_failed", error=str(exc))
                return {"error": "upstream_error", "message": str(exc)}

        housekeeping_summary = {
            "clean": sum(1 for r in rooms if r.housekeeping_status.value in ("clean", "inspected")),
            "dirty": sum(1 for r in rooms if r.housekeeping_status.value == "dirty"),
            "in_progress": sum(1 for r in rooms if r.housekeeping_status.value == "in_progress"),
            "do_not_disturb": sum(1 for r in rooms if r.housekeeping_status.value == "do_not_disturb"),
            "priority": sum(1 for r in rooms if r.priority_clean),
        }

        return {
            "source": "pms",
            "property_id": property_id,
            "count": len(rooms),
            "housekeeping_summary": housekeeping_summary,
            "rooms": [r.model_dump(mode="json") for r in rooms],
        }
