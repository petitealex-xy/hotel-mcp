"""
Hotel MCP Server — entry point.

Wires together tools, resources, and prompts onto a single FastMCP instance
and starts the stdio transport for communication with MCP clients
(Claude Desktop, Claude Code, custom integrations).

Run:
    python -m src.server
    # or via the project script:
    hotel-mcp
"""

from __future__ import annotations

import logging
import sys

import structlog
from mcp.server.fastmcp import FastMCP

from src.config import settings
from src.prompts.hotel_prompts import register_prompts
from src.resources.hotel_resources import register_resources
from src.tools.guest_tools import register_guest_tools
from src.tools.reservation_tools import register_reservation_tools
from src.tools.room_tools import register_room_tools
from src.tools.sync_tools import register_sync_tools

# ── Structured logging setup ──────────────────────────────────────────────────

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.server.log_level.upper(), logging.INFO)
    ),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

logger = structlog.get_logger(__name__)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name=settings.server.server_name,
    instructions=(
        "You are connected to the Hotel Operations MCP Server. "
        "This server provides read-only access to guest profiles, reservations, "
        "room status, and data reconciliation tools across PMS and CRM systems. "
        "\n\n"
        "Key capabilities:\n"
        "- get_guest_from_pms / get_guest_from_crm — fetch guest profiles\n"
        "- compare_guest_records — detect PMS↔CRM discrepancies\n"
        "- generate_guest_unified_view — single canonical guest record\n"
        "- get_reservation — full reservation details\n"
        "- get_room_status / list_rooms — occupancy and housekeeping\n"
        "- suggest_sync_actions — safe, human-approved reconciliation plan\n"
        "- find_duplicate_records — detect duplicate guest records\n"
        "\n"
        "All write operations are disabled by default. "
        "Guest data is subject to GDPR — consult hotel://policy/data-handling "
        "before displaying sensitive fields."
    ),
)

# ── Register tools ────────────────────────────────────────────────────────────

register_guest_tools(mcp)
register_reservation_tools(mcp)
register_room_tools(mcp)
register_sync_tools(mcp)

# ── Register resources ────────────────────────────────────────────────────────

register_resources(mcp)

# ── Register prompts ──────────────────────────────────────────────────────────

register_prompts(mcp)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info(
        "hotel_mcp_server_starting",
        server_name=settings.server.server_name,
        environment=settings.server.env,
        pms_adapter=settings.pms.adapter,
        crm_adapter=settings.crm.adapter,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    import sys
    import os
    # Ensure project root is on the path when run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
