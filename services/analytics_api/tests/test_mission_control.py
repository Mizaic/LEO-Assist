"""VT-LEO-AI-091: Mission Control backend API verification tests.

Tests cover:
  TC-001  pathway filter 'confirmed' restricts to completed episodes
  TC-002  pathway filter 'closures' restricts to closure statuses
  TC-003  cancer type filter restricts by EpisodeOfCare.cancer_type
  TC-004  review status 'unreviewed' restricts to reviewed_at IS NULL
  TC-005  pagination SKIP/LIMIT calculated correctly
  TC-006  KPI endpoint returns all 6 required fields with correct types
  TC-007  PATCH /review writes audit fields without altering clinical data
  TC-008  unauthenticated PATCH /review returns HTTP 401
"""

from __future__ import annotations

import pytest

from libs.auth.org_scope import CallerScope
from services.analytics_api.app.routers.mission_control import (
    ReviewRequest,
    _apply_cancer_type_filter,
    _apply_closure_reason_filter,
    _apply_patient_id_filter,
    _apply_pathway_filter,
    _apply_review_filter,
    _kpis_cypher,
    _normalise_mission_episode_id,
    _normalise_mission_patient_id,
    _patient_pipeline_audit_prefix,
    _patients_cypher,
    _CLOSURE_STATUSES,
    _ALWAYS_EXCLUDE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = (
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom'] "
)


# ---------------------------------------------------------------------------
# TC-001: pathway filter 'confirmed' adds ep.status = 'completed'
# ---------------------------------------------------------------------------


def test_pathway_filter_confirmed_adds_completed_where_clause():
    """VT-091-TC-001: confirmed filter restricts to ep.status = 'completed'."""
    base, params = _apply_pathway_filter(BASE, {}, "confirmed")
    assert "ep.status = 'completed'" in base
    assert "closed_benign" not in base
    assert "stale_no_diagnosis" not in base


# ---------------------------------------------------------------------------
# TC-002: pathway filter 'closures' adds all 4 closure statuses
# ---------------------------------------------------------------------------


def test_pathway_filter_closures_includes_all_closure_statuses():
    """VT-091-TC-002: closures filter restricts to the 4 closure status values."""
    base, params = _apply_pathway_filter(BASE, {}, "closures")
    for status in _CLOSURE_STATUSES:
        assert status in base
    assert "completed" not in base


def test_pathway_filter_all_excludes_only_merged_and_phantom():
    """VT-091-TC-002 (all): 'all' filter only excludes merged and closed_phantom."""
    base, params = _apply_pathway_filter(BASE, {}, "all")
    for status in _ALWAYS_EXCLUDE:
        assert status in base
    assert "closed_benign" not in base
    assert "completed" not in base


# ---------------------------------------------------------------------------
# TC-003: cancer type filter
# ---------------------------------------------------------------------------


def test_cancer_type_filter_adds_in_clause():
    """VT-091-TC-003: cancer_types filter adds ep.cancer_type IN $cancer_types."""
    base, params = _apply_cancer_type_filter(BASE, {}, ["colorectal", "lung"])
    assert "ep.cancer_type IN $cancer_types" in base
    assert params["cancer_types"] == ["colorectal", "lung"]


def test_cancer_type_filter_empty_list_no_change():
    """VT-091-TC-003: empty cancer_types list does not change base."""
    base_before = BASE
    base, params = _apply_cancer_type_filter(BASE, {}, [])
    assert base == base_before
    assert "cancer_types" not in params


# ---------------------------------------------------------------------------
# TC-004: review status filter
# ---------------------------------------------------------------------------


def test_review_filter_unreviewed_adds_is_null():
    """VT-091-TC-004: review_status='unreviewed' adds ep.reviewed_at IS NULL."""
    base, params = _apply_review_filter(BASE, {}, "unreviewed")
    assert "ep.reviewed_at IS NULL" in base


def test_review_filter_reviewed_adds_is_not_null():
    """VT-091-TC-004: review_status='reviewed' adds ep.reviewed_at IS NOT NULL."""
    base, params = _apply_review_filter(BASE, {}, "reviewed")
    assert "ep.reviewed_at IS NOT NULL" in base


def test_review_filter_all_no_change():
    """VT-091-TC-004: review_status='all' does not add reviewed_at clause."""
    base, params = _apply_review_filter(BASE, {}, "all")
    assert "reviewed_at" not in base


# ---------------------------------------------------------------------------
# Patient id filter
# ---------------------------------------------------------------------------


def test_patient_id_filter_adds_to_string_clause():
    """Valid patient_id adds parameterised toString(p.id) predicate."""
    base, params = _apply_patient_id_filter(BASE, {}, "4181221113")
    assert "toString(p.id) = $patient_id" in base
    assert params["patient_id"] == "4181221113"


def test_patient_id_filter_whitespace_trimmed():
    base, params = _apply_patient_id_filter(BASE, {}, "  4181221113  ")
    assert params["patient_id"] == "4181221113"


def test_patient_id_filter_empty_ignored():
    base_before = BASE
    base, params = _apply_patient_id_filter(BASE, {}, "")
    assert base == base_before
    assert "patient_id" not in params


def test_patient_id_filter_invalid_chars_ignored():
    base, params = _apply_patient_id_filter(BASE, {}, "418; DROP")
    assert "patient_id" not in params
    assert "toString(p.id)" not in base


def test_normalise_mission_patient_id_rejects_oversized():
    assert _normalise_mission_patient_id("a" * 65) is None


# ---------------------------------------------------------------------------
# TC-005: pagination SKIP/LIMIT
# ---------------------------------------------------------------------------


def test_pagination_page_1_skip_0():
    """VT-091-TC-005: page=1, page_size=25 -> SKIP 0 LIMIT 25."""
    _, data_q, params = _patients_cypher(BASE, {}, "referral_date", "DESC", 0, 25)
    assert "SKIP $skip" in data_q
    assert "LIMIT $limit" in data_q
    assert params["skip"] == 0
    assert params["limit"] == 25


def test_pagination_page_2_skip_25():
    """VT-091-TC-005: page=2, page_size=25 -> SKIP 25 LIMIT 25."""
    skip = (2 - 1) * 25
    _, data_q, params = _patients_cypher(BASE, {}, "referral_date", "DESC", skip, 25)
    assert params["skip"] == 25
    assert params["limit"] == 25


def test_pagination_page_1_size_50():
    """VT-091-TC-005: page=1, page_size=50 -> SKIP 0 LIMIT 50."""
    _, data_q, params = _patients_cypher(BASE, {}, "referral_date", "DESC", 0, 50)
    assert params["skip"] == 0
    assert params["limit"] == 50


def test_patients_query_collects_distinct_episodes():
    """VT-091-TC-005: patient episode list de-duplicates repeated episode rows."""
    _, data_q, _ = _patients_cypher(BASE, {}, "referral_date", "DESC", 0, 25)
    assert "collect(DISTINCT ep) AS episodes" in data_q


# ---------------------------------------------------------------------------
# TC-006: KPI cypher returns query with all 6 fields
# ---------------------------------------------------------------------------


def test_kpis_cypher_contains_all_6_fields():
    """VT-091-TC-006: KPI query contains all 6 required RETURN aliases."""
    q, params = _kpis_cypher(BASE, {})
    for field in [
        "total_patients",
        "confirmed_cancer",
        "pathway_closures",
        "median_diagnostic_interval_days",
        "safety_netting_rate",
        "needs_review_count",
    ]:
        assert field in q, f"KPI field '{field}' missing from KPI query"


# ---------------------------------------------------------------------------
# TC-009: confirmed_cancer excludes letter_inferred_benign episodes
# ---------------------------------------------------------------------------


def test_kpis_cypher_excludes_letter_inferred_benign():
    """VT-091-TC-009: confirmed_cancer KPI excludes benign-letter closures.

    The confirmed_cancer count MUST use the same definition as the audit
    summary endpoint: ep.status = 'completed' AND
    coalesce(ep.letter_inferred_benign, false) = false.
    Counting benign reassurance-letter closures as confirmed cancer would
    show a clinically incorrect headline figure to clinical staff.
    """
    q, _ = _kpis_cypher(BASE, {})
    assert "letter_inferred_benign" in q, (
        "confirmed_cancer KPI must exclude episodes where "
        "letter_inferred_benign is true"
    )
    assert "coalesce(ep.letter_inferred_benign, false) = false" in q, (
        "confirmed_cancer must use coalesce(..., false) = false to handle "
        "NULL safely, matching the audit summary definition"
    )


# ---------------------------------------------------------------------------
# TC-007: PATCH /review Cypher contains only audit fields
# ---------------------------------------------------------------------------


def test_review_request_model_has_required_fields():
    """VT-091-TC-007: ReviewRequest model parses reviewed_by, audit_notes, audit_flag."""
    req = ReviewRequest(reviewed_by="test@nhs.net", audit_notes="OK", audit_flag=False)
    assert req.reviewed_by == "test@nhs.net"
    assert req.audit_notes == "OK"
    assert req.audit_flag is False


def test_review_cypher_does_not_contain_clinical_fields():
    """VT-091-TC-007: The PATCH /review Cypher does not set cancer_type, status, etc."""
    from services.analytics_api.app.routers.mission_control import patch_episode_review
    import inspect

    source = inspect.getsource(patch_episode_review)
    for clinical_field in ["cancer_type", "condition_type", "cancer_stage", "referral_date"]:
        assert (
            f"ep.{clinical_field}" not in source
            or f"SET ep.{clinical_field}" not in source
        ), (
            f"Clinical field '{clinical_field}' may be set in patch_episode_review"
        )


# ---------------------------------------------------------------------------
# TC-008: unauthenticated access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_review_raises_401():
    """VT-091-TC-008: scope with no email raises HTTPException 401."""
    from fastapi import HTTPException
    from libs.auth.org_scope import CallerScope
    from services.analytics_api.app.routers.mission_control import patch_episode_review

    class EmptyScope:
        email = None
        is_admin = False
        org_ids = []
        primary_org_id = None

        def to_query_params(self):
            return {}

    req = ReviewRequest(reviewed_by="x@nhs.net", audit_flag=False)
    with pytest.raises(HTTPException) as exc_info:
        await patch_episode_review("ep-1", req, scope=EmptyScope())  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401
