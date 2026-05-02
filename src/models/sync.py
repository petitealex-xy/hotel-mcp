"""Data-sync and reconciliation models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DiffSeverity(StrEnum):
    INFO = "info"         # one side is None but the other has data
    WARNING = "warning"   # values differ, low risk to update
    CONFLICT = "conflict" # values differ and both sides are non-null


class AuthoritativeSource(StrEnum):
    PMS = "pms"
    CRM = "crm"
    MANUAL = "manual"     # requires human decision
    LATEST = "latest"     # whichever was updated most recently


class FieldDiff(BaseModel):
    """A single field mismatch between PMS and CRM records."""

    field: str
    field_label: str
    pms_value: Any | None = None
    crm_value: Any | None = None
    severity: DiffSeverity
    recommended_source: AuthoritativeSource
    reason: str  # human-readable explanation for the recommendation


class SyncActionType(StrEnum):
    UPDATE_PMS = "update_pms"
    UPDATE_CRM = "update_crm"
    MERGE_RECORDS = "merge_records"
    FLAG_FOR_REVIEW = "flag_for_review"
    NO_ACTION = "no_action"


class SyncAction(BaseModel):
    """
    A single proposed sync action.
    All actions are suggestions — nothing is executed unless the caller
    explicitly invokes a write tool (which is gated by authorisation).
    """

    action_id: str
    action_type: SyncActionType
    target_system: str  # "pms" | "crm" | "both" | "manual"
    field: str
    current_value: Any | None = None
    proposed_value: Any | None = None
    authoritative_source: AuthoritativeSource
    risk_level: str = "low"   # "low" | "medium" | "high"
    rationale: str
    requires_approval: bool = True
    reversible: bool = True


class SyncPlan(BaseModel):
    """
    A complete, ordered list of sync actions for a guest record.
    Safe to share with staff — nothing is mutated until they approve.
    """

    plan_id: str
    pms_id: str | None = None
    crm_id: str | None = None
    guest_name: str
    generated_at: str  # ISO-8601

    diffs: list[FieldDiff] = Field(default_factory=list)
    actions: list[SyncAction] = Field(default_factory=list)

    total_conflicts: int = 0
    total_warnings: int = 0
    has_high_risk_actions: bool = False
    summary: str = ""

    # Always read-only until this flag is set by an authorised write tool
    write_enabled: bool = False
