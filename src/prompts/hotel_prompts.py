"""
MCP prompts — reusable, parameterised templates for hotel staff workflows.

Prompts are different from tools: they return a structured conversation
starter (system + user messages) that the MCP client injects into the
AI assistant's context. They define *how to think about a task*, while
tools provide *data access*.
"""

from __future__ import annotations

import mcp.types as types
from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:

    # ── Check-in preparation ─────────────────────────────────────────────────

    @mcp.prompt(
        name="check_in_preparation",
        description=(
            "Prepare a comprehensive pre-arrival briefing for a specific guest. "
            "Fetches unified profile, reservation, room status, and outstanding requests."
        ),
    )
    async def check_in_preparation(
        pms_guest_id: str,
        reservation_id: str,
        language: str = "en",
    ) -> list[types.PromptMessage]:
        system_text = (
            "You are a knowledgeable hotel concierge assistant helping front-desk staff "
            "prepare for a guest's arrival. You have access to the PMS and CRM through "
            "hotel MCP tools. Always respect guest privacy — do not display passport numbers "
            "or financial details unless the staff member has the appropriate role. "
            f"Respond in: {language}."
        )
        user_text = (
            f"Please prepare a check-in briefing for guest PMS ID {pms_guest_id!r}, "
            f"reservation {reservation_id!r}. "
            "Include: (1) unified guest profile with data quality flags, "
            "(2) reservation summary and special requests, "
            "(3) room status and readiness, "
            "(4) VIP or loyalty notes, "
            "(5) any outstanding sync issues between PMS and CRM, "
            "(6) suggested personalisation touches based on preferences and past stays. "
            "Flag any missing required data."
        )
        return [
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=system_text + "\n\n" + user_text)),
        ]

    # ── Reconcile guest data ─────────────────────────────────────────────────

    @mcp.prompt(
        name="reconcile_guest_data",
        description=(
            "Guide staff through resolving data conflicts between PMS and CRM "
            "for a specific guest, producing a final approved sync plan."
        ),
    )
    async def reconcile_guest_data(
        pms_id: str,
        crm_id: str,
        language: str = "en",
    ) -> list[types.PromptMessage]:
        system_text = (
            "You are a hotel data quality specialist. Your role is to help staff identify "
            "and resolve conflicts between the PMS and CRM guest records. "
            "Never execute writes on your own — always present a human-readable plan "
            "and ask for explicit approval. Prioritise GDPR-compliant decisions. "
            f"Respond in: {language}."
        )
        user_text = (
            f"Review the guest records for PMS ID {pms_id!r} and CRM ID {crm_id!r}. "
            "Steps: "
            "1. Fetch both profiles using get_guest_from_pms and get_guest_from_crm. "
            "2. Run compare_guest_records and list all differences. "
            "3. Call suggest_sync_actions to get the full reconciliation plan. "
            "4. Present the plan to me clearly — group by risk level (high/medium/low). "
            "5. For each high-risk action, explain the consequences of getting it wrong. "
            "6. Ask me to confirm before any action is marked as approved. "
            "Do not proceed to write anything — this session is read-only."
        )
        return [
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=system_text + "\n\n" + user_text)),
        ]

    # ── Housekeeping briefing ────────────────────────────────────────────────

    @mcp.prompt(
        name="housekeeping_briefing",
        description=(
            "Generate a prioritised housekeeping task list for a floor or property, "
            "highlighting VIP arrivals and rooms needing urgent attention."
        ),
    )
    async def housekeeping_briefing(
        property_id: str,
        floor: str | None = None,
        language: str = "en",
    ) -> list[types.PromptMessage]:
        system_text = (
            "You are a housekeeping coordinator assistant. Help supervisors prioritise "
            "room cleaning efficiently. Focus on: VIP arrivals, early check-in requests, "
            "rooms with special setup requirements, and maintenance issues. "
            f"Respond in: {language}."
        )
        scope = f"floor {floor}" if floor else f"the entire property {property_id!r}"
        user_text = (
            f"Please generate today's housekeeping briefing for {scope}. "
            "1. Call list_rooms to get the current room status overview. "
            "2. Identify all 'dirty' rooms — sort by priority (VIP arrival > early check-in > standard). "
            "3. List rooms 'in_progress' and estimate completion if attendant is assigned. "
            "4. Flag any 'do_not_disturb' or 'refused' rooms that may need a revisit later. "
            "5. Highlight maintenance issues that block room availability. "
            "6. Produce a concise shift handover note."
        )
        return [
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=system_text + "\n\n" + user_text)),
        ]

    # ── Guest complaint triage ───────────────────────────────────────────────

    @mcp.prompt(
        name="guest_complaint_triage",
        description=(
            "Help staff look up a guest, review their stay history and preferences, "
            "and draft an appropriate service-recovery response."
        ),
    )
    async def guest_complaint_triage(
        guest_email: str,
        complaint_summary: str,
        language: str = "en",
    ) -> list[types.PromptMessage]:
        system_text = (
            "You are a guest relations specialist. You help resolve complaints empathetically "
            "and according to the hotel's service recovery policy. Always check loyalty status "
            "and total stays before proposing compensation — high-value guests warrant elevated "
            "responses. Follow GDPR rules: do not log or share complaint details externally. "
            f"Respond in: {language}."
        )
        user_text = (
            f"A guest has raised a complaint. Email: {guest_email!r}. "
            f"Complaint summary: {complaint_summary!r}. "
            "1. Look up the guest in the PMS and CRM using their email. "
            "2. Review loyalty tier, total stays, and most recent reservation. "
            "3. Check for any outstanding data quality issues that might have contributed. "
            "4. Draft a personalised service-recovery response appropriate to their loyalty tier. "
            "5. Suggest concrete remediation steps (upgrade, F&B credit, follow-up call). "
            "6. Note whether the complaint suggests a systemic process issue to escalate."
        )
        return [
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=system_text + "\n\n" + user_text)),
        ]

    # ── VIP arrival alert ────────────────────────────────────────────────────

    @mcp.prompt(
        name="vip_arrival_alert",
        description=(
            "Scan today's arrivals and produce a VIP alert sheet with personalised "
            "service notes for each high-value guest."
        ),
    )
    async def vip_arrival_alert(
        property_id: str,
        language: str = "en",
    ) -> list[types.PromptMessage]:
        system_text = (
            "You are a luxury hotel GM's assistant. Your job is to ensure VIP guests receive "
            "a flawless, personalised experience. Be concise — GMs read these alerts quickly. "
            f"Respond in: {language}."
        )
        user_text = (
            f"Property: {property_id!r}. "
            "Compile today's VIP arrival sheet: "
            "1. From the PMS, identify reservations with is_vip=true or loyalty_tier=platinum arriving today. "
            "2. For each VIP, fetch their unified profile from both PMS and CRM. "
            "3. Highlight: preferred room type, dietary requirements, special occasions, languages spoken. "
            "4. Note any data quality issues (e.g. missing preferences, sync conflicts). "
            "5. Suggest one personalised gesture for each guest based on their history. "
            "Format as a clean briefing table followed by per-guest notes."
        )
        return [
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=system_text + "\n\n" + user_text)),
        ]
