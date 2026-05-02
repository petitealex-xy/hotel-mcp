"""
Guest record reconciliation engine.

Compares a PMSGuest against a CRMGuest field-by-field, produces a list of
FieldDiff objects, computes a data-quality score, and generates a SyncPlan
with actionable (but never auto-executed) suggestions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.models.guest import (
    RECONCILABLE_FIELDS,
    CRMGuest,
    DataQualityFlag,
    GuestPreferences,
    PMSGuest,
    UnifiedGuestView,
)
from src.models.sync import (
    AuthoritativeSource,
    DiffSeverity,
    FieldDiff,
    SyncAction,
    SyncActionType,
    SyncPlan,
)


def _str(v: Any) -> str:
    return str(v).strip().lower() if v is not None else ""


def _compare_field(
    field: str,
    label: str,
    pms_val: Any,
    crm_val: Any,
) -> FieldDiff | None:
    """Return a FieldDiff if the values differ, else None."""
    pms_s, crm_s = _str(pms_val), _str(crm_val)

    if pms_s == crm_s:
        return None

    if not pms_s and crm_s:
        return FieldDiff(
            field=field,
            field_label=label,
            pms_value=None,
            crm_value=crm_val,
            severity=DiffSeverity.INFO,
            recommended_source=AuthoritativeSource.CRM,
            reason=f"{label} is missing in PMS but present in CRM — copy CRM value to PMS.",
        )

    if pms_s and not crm_s:
        return FieldDiff(
            field=field,
            field_label=label,
            pms_value=pms_val,
            crm_value=None,
            severity=DiffSeverity.INFO,
            recommended_source=AuthoritativeSource.PMS,
            reason=f"{label} is missing in CRM but present in PMS — copy PMS value to CRM.",
        )

    # Both sides have a value but they disagree
    severity = DiffSeverity.CONFLICT

    # Loyalty tier is authoritative in the PMS (transactional source of truth)
    if field == "loyalty_tier":
        return FieldDiff(
            field=field,
            field_label=label,
            pms_value=pms_val,
            crm_value=crm_val,
            severity=severity,
            recommended_source=AuthoritativeSource.PMS,
            reason=(
                "Loyalty tier is computed from stay history in the PMS. "
                "PMS value takes precedence — update CRM to match."
            ),
        )

    # Email conflicts are high-stakes; flag for manual review
    if field == "email":
        return FieldDiff(
            field=field,
            field_label=label,
            pms_value=pms_val,
            crm_value=crm_val,
            severity=severity,
            recommended_source=AuthoritativeSource.MANUAL,
            reason=(
                "Email addresses differ across systems. "
                "Manual verification required before overwriting either record."
            ),
        )

    return FieldDiff(
        field=field,
        field_label=label,
        pms_value=pms_val,
        crm_value=crm_val,
        severity=severity,
        recommended_source=AuthoritativeSource.LATEST,
        reason=(
            f"{label} values differ. Review both and keep the most recently updated version."
        ),
    )


def compare_records(pms: PMSGuest, crm: CRMGuest) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    pms_d = pms.model_dump()
    crm_d = crm.model_dump()

    for field, label in RECONCILABLE_FIELDS:
        diff = _compare_field(field, label, pms_d.get(field), crm_d.get(field))
        if diff:
            diffs.append(diff)

    return diffs


def _diff_to_action(diff: FieldDiff, pms: PMSGuest, crm: CRMGuest) -> SyncAction:
    if diff.recommended_source == AuthoritativeSource.PMS:
        action_type = SyncActionType.UPDATE_CRM
        target = "crm"
        proposed = diff.pms_value
        current = diff.crm_value
    elif diff.recommended_source == AuthoritativeSource.CRM:
        action_type = SyncActionType.UPDATE_PMS
        target = "pms"
        proposed = diff.crm_value
        current = diff.pms_value
    else:
        action_type = SyncActionType.FLAG_FOR_REVIEW
        target = "manual"
        proposed = None
        current = None

    risk = "high" if diff.severity == DiffSeverity.CONFLICT else "low"
    requires_approval = diff.severity == DiffSeverity.CONFLICT

    return SyncAction(
        action_id=str(uuid.uuid4()),
        action_type=action_type,
        target_system=target,
        field=diff.field,
        current_value=current,
        proposed_value=proposed,
        authoritative_source=diff.recommended_source,
        risk_level=risk,
        rationale=diff.reason,
        requires_approval=requires_approval,
        reversible=True,
    )


def build_sync_plan(pms: PMSGuest, crm: CRMGuest) -> SyncPlan:
    diffs = compare_records(pms, crm)
    actions = [_diff_to_action(d, pms, crm) for d in diffs]
    conflicts = sum(1 for d in diffs if d.severity == DiffSeverity.CONFLICT)
    warnings = sum(1 for d in diffs if d.severity == DiffSeverity.WARNING)
    high_risk = any(a.risk_level == "high" for a in actions)

    if not diffs:
        summary = "Records are in sync — no action required."
    else:
        summary = (
            f"Found {len(diffs)} difference(s): "
            f"{conflicts} conflict(s), {warnings} warning(s). "
            f"Review the proposed actions before applying any changes."
        )

    return SyncPlan(
        plan_id=str(uuid.uuid4()),
        pms_id=pms.pms_id,
        crm_id=crm.crm_id,
        guest_name=f"{pms.first_name} {pms.last_name}",
        generated_at=datetime.now(timezone.utc).isoformat(),
        diffs=diffs,
        actions=actions,
        total_conflicts=conflicts,
        total_warnings=warnings,
        has_high_risk_actions=high_risk,
        summary=summary,
        write_enabled=False,  # always read-only until explicitly unlocked
    )


def build_unified_view(pms: PMSGuest, crm: CRMGuest) -> UnifiedGuestView:
    """
    Merge PMS and CRM data into a single canonical view.
    PMS wins for transactional fields; CRM wins for preference and consent fields.
    """
    from src.models.guest import DataQualityFlag

    flags: list[DataQualityFlag] = []
    missing: list[str] = []
    notes: list[str] = []

    # Identity — PMS is primary source for transactional identity
    email = pms.email or crm.email
    if not email:
        flags.append(DataQualityFlag.MISSING_EMAIL)
        missing.append("email")
    elif pms.email and crm.email and pms.email.lower() != crm.email.lower():
        flags.append(DataQualityFlag.EMAIL_MISMATCH)
        notes.append(f"Email mismatch: PMS={pms.email!r}, CRM={crm.email!r}. Using PMS value.")

    phone = pms.phone or crm.phone
    if not phone:
        flags.append(DataQualityFlag.MISSING_PHONE)
        missing.append("phone")

    dob = pms.date_of_birth or crm.date_of_birth
    if not dob:
        flags.append(DataQualityFlag.MISSING_DOB)
        missing.append("date_of_birth")

    if not pms.nationality:
        flags.append(DataQualityFlag.MISSING_NATIONALITY)
        missing.append("nationality")

    if not crm.gdpr_consent:
        flags.append(DataQualityFlag.MISSING_GDPR_CONSENT)

    # Loyalty — PMS is authoritative (computed from actual stay history)
    if pms.loyalty_tier != crm.loyalty_tier:
        flags.append(DataQualityFlag.LOYALTY_TIER_MISMATCH)
        notes.append(
            f"Loyalty tier mismatch: PMS={pms.loyalty_tier}, CRM={crm.loyalty_tier}. "
            "PMS value used — CRM should be updated."
        )

    name_match = (
        pms.first_name.strip().lower() == crm.first_name.strip().lower()
        and pms.last_name.strip().lower() == crm.last_name.strip().lower()
    )
    if not name_match:
        flags.append(DataQualityFlag.NAME_MISMATCH)
        notes.append(
            f"Name mismatch: PMS={pms.first_name} {pms.last_name!r}, "
            f"CRM={crm.first_name} {crm.last_name!r}."
        )

    # Confidence drops with every flag
    confidence = max(0.0, 1.0 - len(flags) * 0.1)

    return UnifiedGuestView(
        pms_id=pms.pms_id,
        crm_id=crm.crm_id,
        full_name=f"{pms.first_name} {pms.last_name}",
        email=email,
        phone=phone,
        date_of_birth=dob,
        gender=pms.gender,
        nationality=pms.nationality,
        preferred_language=crm.preferred_language,
        loyalty_number=pms.loyalty_number or crm.loyalty_number,
        loyalty_tier=pms.loyalty_tier,  # PMS authoritative
        segment=crm.segment,
        total_stays=pms.total_stays,
        total_revenue=pms.total_revenue,
        currency=pms.currency,
        last_stay_date=pms.last_stay_date,
        preferences=crm.preferences,
        gdpr_consent=crm.gdpr_consent,
        marketing_opt_in=crm.marketing_opt_in,
        quality_flags=flags,
        confidence_score=confidence,
        missing_fields=missing,
        reconciliation_notes=notes,
    )
