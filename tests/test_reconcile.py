"""
Unit tests for the reconciliation engine.
No network calls — uses mock adapters only.
"""

import pytest

from src.adapters.crm.mock import MockCRMAdapter
from src.adapters.pms.mock import MockPMSAdapter
from src.models.guest import DataQualityFlag, LoyaltyTier
from src.models.sync import AuthoritativeSource, DiffSeverity, SyncActionType
from src.utils.reconcile import build_sync_plan, build_unified_view, compare_records


@pytest.fixture
def pms():
    return MockPMSAdapter()


@pytest.fixture
def crm():
    return MockCRMAdapter()


class TestCompareRecords:
    async def test_in_sync_guest_produces_no_diffs(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-001")
        crm_guest = await crm.get_contact_by_id("CRM-001")
        diffs = compare_records(pms_guest, crm_guest)
        # Marie Dupont — both systems agree on all reconcilable fields
        assert len(diffs) == 0

    async def test_mismatched_loyalty_tier_is_conflict(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")  # PLATINUM
        crm_guest = await crm.get_contact_by_id("CRM-003")  # GOLD
        diffs = compare_records(pms_guest, crm_guest)

        tier_diff = next(d for d in diffs if d.field == "loyalty_tier")
        assert tier_diff.severity == DiffSeverity.CONFLICT
        assert tier_diff.recommended_source == AuthoritativeSource.PMS

    async def test_email_mismatch_requires_manual_review(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")
        crm_guest = await crm.get_contact_by_id("CRM-003")
        diffs = compare_records(pms_guest, crm_guest)

        email_diff = next(d for d in diffs if d.field == "email")
        assert email_diff.severity == DiffSeverity.CONFLICT
        assert email_diff.recommended_source == AuthoritativeSource.MANUAL


class TestSyncPlan:
    async def test_sync_plan_is_always_read_only(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")
        crm_guest = await crm.get_contact_by_id("CRM-003")
        plan = build_sync_plan(pms_guest, crm_guest)
        assert plan.write_enabled is False

    async def test_high_risk_flag_raised_on_email_conflict(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")
        crm_guest = await crm.get_contact_by_id("CRM-003")
        plan = build_sync_plan(pms_guest, crm_guest)
        assert plan.has_high_risk_actions is True

    async def test_email_conflict_action_requires_approval(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")
        crm_guest = await crm.get_contact_by_id("CRM-003")
        plan = build_sync_plan(pms_guest, crm_guest)
        email_actions = [a for a in plan.actions if a.field == "email"]
        assert all(a.requires_approval for a in email_actions)

    async def test_no_diffs_gives_clean_summary(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-001")
        crm_guest = await crm.get_contact_by_id("CRM-001")
        plan = build_sync_plan(pms_guest, crm_guest)
        assert plan.total_conflicts == 0
        assert "in sync" in plan.summary.lower()


class TestUnifiedView:
    async def test_pms_loyalty_tier_wins(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")  # PLATINUM
        crm_guest = await crm.get_contact_by_id("CRM-003")  # GOLD
        view = build_unified_view(pms_guest, crm_guest)
        assert view.loyalty_tier == LoyaltyTier.PLATINUM

    async def test_loyalty_mismatch_raises_flag(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-003")
        crm_guest = await crm.get_contact_by_id("CRM-003")
        view = build_unified_view(pms_guest, crm_guest)
        assert DataQualityFlag.LOYALTY_TIER_MISMATCH in view.quality_flags

    async def test_confidence_is_lower_for_mismatched_records(self, pms, crm):
        pms_clean = await pms.get_guest_by_id("PMS-001")
        crm_clean = await crm.get_contact_by_id("CRM-001")
        clean_view = build_unified_view(pms_clean, crm_clean)

        pms_conflict = await pms.get_guest_by_id("PMS-003")
        crm_conflict = await crm.get_contact_by_id("CRM-003")
        conflict_view = build_unified_view(pms_conflict, crm_conflict)

        assert conflict_view.confidence_score < clean_view.confidence_score

    async def test_crm_preferences_used_in_unified_view(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-001")
        crm_guest = await crm.get_contact_by_id("CRM-001")
        view = build_unified_view(pms_guest, crm_guest)
        assert view.preferences.room_type == "king"
        assert "vegetarian" in view.preferences.dietary_restrictions

    async def test_gdpr_consent_from_crm(self, pms, crm):
        pms_guest = await pms.get_guest_by_id("PMS-001")
        crm_guest = await crm.get_contact_by_id("CRM-001")
        view = build_unified_view(pms_guest, crm_guest)
        assert view.gdpr_consent is True


class TestMockAdapters:
    async def test_pms_guest_not_found_raises(self, pms):
        from src.adapters.pms.base import GuestNotFound
        with pytest.raises(GuestNotFound):
            await pms.get_guest_by_id("PMS-NONEXISTENT")

    async def test_pms_search_returns_partial_matches(self, pms):
        results = await pms.search_guests("tanaka")
        assert any(g.last_name == "Tanaka" for g in results)

    async def test_crm_lookup_by_loyalty_number(self, crm):
        guest = await crm.get_contact_by_loyalty_number("LYL-99001")
        assert guest.crm_id == "CRM-001"
