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
    LIFECYCLE_BUCKET_PATTERN,
    NO_PATHWAY_BUCKET,
    ReviewRequest,
    _apply_cancer_type_filter,
    _apply_closure_reason_filter,
    _apply_lifecycle_bucket_filter,
    _apply_patient_id_filter,
    _patient_only_query,
    _apply_pathway_filter,
    _apply_review_filter,
    _kpis_cypher,
    _no_pathway_patients_cypher,
    _no_pathway_scope_match,
    _normalise_mission_episode_id,
    _normalise_mission_patient_id,
    _patient_pipeline_audit_prefix,
    _patients_cypher,
    get_patient_rebuild_status,
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
# Lifecycle bucket filter (DI-105A4EC7)
# ---------------------------------------------------------------------------


def test_lifecycle_bucket_filter_all_no_change():
    """The wildcard 'all' value must not modify base or params."""
    base_before = BASE
    base, params = _apply_lifecycle_bucket_filter(BASE, {}, "all")
    assert base == base_before
    assert "lifecycle_bucket" not in params


def test_lifecycle_bucket_filter_uses_hero_bucket_case():
    """A real bucket appends a CASE expression bound to $lifecycle_bucket
    so the filter clause is exactly what the dashboard's hero count
    Cypher computed. This is the parity guarantee the contract test
    relies on.
    """
    for bucket in ("active", "in_review", "cancer_excluded", "confirmed_cancer"):
        base, params = _apply_lifecycle_bucket_filter(BASE, {}, bucket)
        assert "= $lifecycle_bucket" in base
        # All four MECE bucket strings appear in the appended CASE.
        for token in (
            "'active'",
            "'in_review'",
            "'cancer_excluded'",
            "'confirmed_cancer'",
        ):
            assert token in base
        assert "letter_inferred_benign" in base
        assert params["lifecycle_bucket"] == bucket


def test_lifecycle_bucket_filter_unknown_bucket_no_change():
    """Defensive: a value not in HERO_BUCKETS must not append anything.
    The endpoint also validates via LIFECYCLE_BUCKET_PATTERN, so this
    branch is only reachable through bypassed validation.
    """
    base_before = BASE
    base, params = _apply_lifecycle_bucket_filter(BASE, {}, "garbage")
    assert base == base_before
    assert "lifecycle_bucket" not in params


def test_lifecycle_bucket_pattern_accepts_only_canonical_buckets():
    """The Query() pattern lets through 'all', the four MECE buckets,
    and 'no_pathway' (DI-CA1B4C6E). Anything else must be rejected so
    an attacker can't smuggle an arbitrary $param value through this
    endpoint.
    """
    import re

    rx = re.compile(LIFECYCLE_BUCKET_PATTERN)
    accepted = (
        "all",
        "active",
        "in_review",
        "cancer_excluded",
        "confirmed_cancer",
        "no_pathway",
    )
    for ok in accepted:
        assert rx.match(ok), ok
    for bad in (
        "",
        "ALL",
        "Active",
        "1=1",
        "active' OR 1=1--",
        "garbage",
        "no-pathway",
        "noPathway",
    ):
        assert not rx.match(bad), bad


# ---------------------------------------------------------------------------
# no_pathway lifecycle bucket (DI-CA1B4C6E)
# ---------------------------------------------------------------------------


def test_no_pathway_bucket_treated_as_no_op_by_episode_filter():
    """The 'no_pathway' bucket is structurally different (matches
    patients-without-EpisodeOfCare) and must NOT append the
    episode-bound CASE clause used by the four MECE buckets, otherwise
    the Cypher would reference a non-existent ``ep`` alias and crash.
    The endpoint dispatches to _no_pathway_scope_match instead.
    """
    base_before = BASE
    base, params = _apply_lifecycle_bucket_filter(
        BASE, {}, NO_PATHWAY_BUCKET
    )
    assert base == base_before
    assert "lifecycle_bucket" not in params


def test_no_pathway_scope_match_admin_no_org_returns_unscoped_match():
    """Admin caller without an org_id sees every Patient node not
    linked to an EpisodeOfCare. The match clause must not bind to any
    organisation parameter.
    """
    scope = CallerScope(email="admin@nhs.net", is_admin=True)
    base, params = _no_pathway_scope_match(None, scope)
    assert "(p:Patient)" in base
    assert "NOT EXISTS" in base
    assert "HAS_EPISODE_OF_CARE" in base
    assert "(:EpisodeOfCare)" in base
    assert params == {}


def test_no_pathway_scope_match_with_org_id_uses_alliance_scope():
    """When an org_id is provided, the no_pathway match clause must
    follow the same practice/ICB/alliance commissioning chain Mission
    Control uses for episode-bound queries -- otherwise the deep-link
    cohort would diverge from the dashboard cohort denominator.
    """
    scope = CallerScope(email="qa@example.com", is_admin=True)
    base, params = _no_pathway_scope_match("ORG-1", scope)
    assert "$org" in base
    assert "HAS_GENERAL_PRACTITIONER" in base
    assert "COMMISSIONED_BY" in base
    assert "PART_OF_ALLIANCE" in base
    assert "NOT EXISTS" in base
    assert params == {"org": "ORG-1"}


def test_no_pathway_patients_cypher_returns_empty_episodes_array():
    """Patients in the no_pathway bucket have no EpisodeOfCare nodes
    by definition. The data query must return an empty episodes
    array literal so _row_to_patient yields a well-formed response
    shape (the UI rendering assumes episodes is always a list).
    """
    base = "MATCH (p:Patient) WHERE NOT EXISTS { (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) } "
    count_q, data_q, params = _no_pathway_patients_cypher(
        base, {"org": "ORG-1"}, skip=0, limit=25
    )
    assert "count(DISTINCT p) AS total" in count_q
    assert "[] AS episodes" in data_q
    assert "ORDER BY p.id" in data_q
    assert "SKIP $skip LIMIT $limit" in data_q
    assert params == {"org": "ORG-1", "skip": 0, "limit": 25}


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


def test_patient_only_query_scopes_exact_id():
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )
    q, params = _patient_only_query(scope, "org-1", "4181221113")
    assert "toString(p.id) = $patient_id" in q
    assert "LIMIT 1" in q
    assert params["patient_id"] == "4181221113"


@pytest.mark.asyncio
async def test_patients_endpoint_falls_back_to_patient_without_episodes(monkeypatch):
    from services.analytics_api.app.routers import mission_control as mc

    class _FakeClient:
        def run(self, query, **kwargs):
            # 1st run: count query returns no episode rows.
            if "count(DISTINCT p) AS total" in query:
                return [{"total": 0}]
            # 2nd run: data query returns no rows.
            if "collect(DISTINCT ep) AS episodes" in query:
                return []
            # 3rd run: fallback patient-only query.
            if "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]" in query:
                return [
                    {
                        "patient_id": "4181221113",
                        "gender": "female",
                        "birth_date": "1985-01-01",
                        "practice_name": "Woodbrook Medical Centre",
                    }
                ]
            return []

        def close(self):
            return None

    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)

    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    result = await mc.get_mission_control_patients(
        org_id="org-1",
        date_from=None,
        date_to=None,
        pathway_filter="all",
        cancer_types=None,
        closure_reasons=None,
        review_status="all",
        patient_id="4181221113",
        sort_by="referral_date",
        sort_dir="DESC",
        page=1,
        page_size=25,
        scope=scope,
    )
    assert result["total"] == 1
    assert len(result["patients"]) == 1
    assert result["patients"][0]["patient_id"] == "4181221113"
    assert result["patients"][0]["episodes"] == []


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
    for clinical_field in [
        "cancer_type",
        "condition_type",
        "cancer_stage",
        "referral_date",
    ]:
        assert (
            f"ep.{clinical_field}" not in source
            or f"SET ep.{clinical_field}" not in source
        ), f"Clinical field '{clinical_field}' may be set in patch_episode_review"


def test_pipeline_events_query_falls_back_when_episode_missing():
    """Episode-scoped audit trail query must fall back to patient-wide runs.

    After a reset, the old EpisodeOfCare can be deleted and rebuilt. The audit
    trail endpoint should still show PipelineRun rows for the patient by using
    OPTIONAL MATCH and allowing empty encounter sets.
    """
    from services.analytics_api.app.routers.mission_control import (
        get_patient_pipeline_events,
    )
    import inspect

    source = inspect.getsource(get_patient_pipeline_events)
    assert "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]" in source
    assert "size(allowed) = 0" in source


# ---------------------------------------------------------------------------
# DI-3A19BE12 -- manual-events endpoint surfaces EpisodeManual* AuditEvents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_events_returns_starts_with_episode_manual():
    """The query MUST filter to EpisodeManual* event_type values so
    PipelineRun rows do not bleed into the Human edits section."""
    from services.analytics_api.app.routers.mission_control import (
        get_patient_manual_events,
    )
    import inspect

    source = inspect.getsource(get_patient_manual_events)
    assert "STARTS WITH 'EpisodeManual'" in source
    assert "ORDER BY ae.created_at DESC" in source


@pytest.mark.asyncio
async def test_manual_events_returns_curator_rows():
    """End-to-end shape: the endpoint maps Cypher rows to the
    ManualAuditEvent JSON schema the UI expects (event_type, actor,
    notes, created_at)."""
    from unittest.mock import patch
    from libs.auth.org_scope import CallerScope
    from services.analytics_api.app.routers.mission_control import (
        get_patient_manual_events,
    )

    fake_rows = [
        {
            "id": "ae-1",
            "event_type": "EpisodeManualAttach",
            "subtype": "episode_manual_edit",
            "created_at": "2026-04-22T09:00:00",
            "actor_email": "rob@example.com",
            "actor_role": "qa_ra_lead",
            "episode_id": "ep-001",
            "patient_id": "P-1",
            "notes": "Attached encounter=enc-1 as milestone=diagnosis_confirmed",
            "before_json": "",
            "after_json": "",
        }
    ]

    with patch(
        "services.analytics_api.app.routers.mission_control.PatientGraphClient"
    ) as MockPG:
        client = MockPG.return_value
        client.run.return_value = fake_rows

        scope = CallerScope(email="x@y", is_admin=True, org_ids=[])
        result = await get_patient_manual_events(
            patient_id="P-1",
            org_id=None,
            episode_id=None,
            limit=40,
            scope=scope,
        )

    assert result["patient_id"] == "P-1"
    assert len(result["events"]) == 1
    ev = result["events"][0]
    assert ev["event_type"] == "EpisodeManualAttach"
    assert ev["actor_email"] == "rob@example.com"
    assert ev["actor_role"] == "qa_ra_lead"
    assert "diagnosis_confirmed" in ev["notes"]


@pytest.mark.asyncio
async def test_manual_events_filters_to_episode_when_specified():
    """When episode_id is supplied the Cypher must add the
    `ae.episode_id = $episode_id OR coalesce(ae.episode_id, '') = ''`
    clause so each episode tab only shows its own audit trail (plus
    the patient-wide create event for that episode)."""
    from unittest.mock import patch
    from libs.auth.org_scope import CallerScope
    from services.analytics_api.app.routers.mission_control import (
        get_patient_manual_events,
    )

    with patch(
        "services.analytics_api.app.routers.mission_control.PatientGraphClient"
    ) as MockPG:
        client = MockPG.return_value
        client.run.return_value = []

        scope = CallerScope(email="x@y", is_admin=True, org_ids=[])
        await get_patient_manual_events(
            patient_id="P-1",
            org_id=None,
            episode_id="ep-001",
            limit=40,
            scope=scope,
        )

        cypher = client.run.call_args[0][0]
        assert "ae.episode_id = $episode_id" in cypher
        assert client.run.call_args.kwargs["episode_id"] == "ep-001"


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


@pytest.mark.asyncio
async def test_patient_rebuild_status_returns_estimates(monkeypatch):
    from services.analytics_api.app.routers import mission_control as mc

    class _FakeClient:
        def run(self, query, **kwargs):
            if "RETURN count(p) AS c LIMIT 1" in query:
                return [{"c": 1}]
            if "total_duration_ms AS total_duration_ms" in query:
                return [
                    {"total_duration_ms": 60000, "created_at": "2026-04-10T10:00:00Z"},
                    {"total_duration_ms": 90000, "created_at": "2026-04-10T10:01:00Z"},
                ]
            return []

        def close(self):
            return None

    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)
    monkeypatch.setattr(mc, "_pipeline_queue_depth", lambda: 12)
    monkeypatch.setattr(
        mc,
        "get_rebuild_status",
        lambda _pid: {
            "run_id": "run-123",
            "status": "queued",
            "message": "Queued and waiting for worker pickup.",
            "updated_at": "2026-04-10T10:00:00Z",
            "queued_jobs": 3,
        },
    )

    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )
    result = await get_patient_rebuild_status("4181221113", "org-1", scope)
    assert result["status"] == "queued"
    assert result["queue_depth"] == 12
    assert result["queue_position_estimate"] == 11
    assert result["eta_seconds_estimate"] is not None
