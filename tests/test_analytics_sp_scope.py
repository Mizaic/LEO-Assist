"""Analytics SP cohort scope assertions for _ORG_PATIENT_MATCH / _patient_base."""

from __future__ import annotations

from libs.auth.org_scope import CallerScope
from services.analytics_api.app.routers._audit_helpers import (
    _ORG_PATIENT_MATCH,
    _patient_base,
)


def test_org_patient_match_includes_sp_referral_arms() -> None:
    assert "PROVIDES_SERVICE" in _ORG_PATIENT_MATCH
    assert "ReferralRequest" in _ORG_PATIENT_MATCH
    assert "HAS_GENERAL_PRACTITIONER" in _ORG_PATIENT_MATCH
    assert "PROVIDES_SERVICE_FOR" not in _ORG_PATIENT_MATCH


def test_patient_base_explicit_org_includes_sp_arms() -> None:
    scope = CallerScope(
        email="admin@test.ai",
        is_admin=True,
        org_ids=[],
        scope_type=None,
        primary_org_id=None,
    )
    clause, params = _patient_base("M0L1I", scope)
    assert params == {"org": "M0L1I"}
    assert "PROVIDES_SERVICE" in clause
    assert "ReferralRequest" in clause
    assert "HAS_GENERAL_PRACTITIONER" in clause


def test_patient_base_gp_admin_unchanged_shape() -> None:
    scope = CallerScope(
        email="admin@test.ai",
        is_admin=True,
        org_ids=[],
        scope_type=None,
        primary_org_id=None,
    )
    clause, params = _patient_base("D83007", scope)
    assert params == {"org": "D83007"}
    assert "HAS_GENERAL_PRACTITIONER" in clause
    assert "COMMISSIONED_BY" in clause
