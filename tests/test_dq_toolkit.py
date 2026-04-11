"""VT-LEO-AI-089 -- Data Quality Toolkit verification tests.

Tests cover:
  TC-001: Episode health returns status distribution
  TC-002: Outcome inference produces correct verdicts
  TC-003: DQ rules engine produces scorecard
  TC-004: Remediation dry-run returns preview without writing
  TC-005: Signal patterns module loads and matches
  TC-006: Surface form audit returns health metrics
  TC-007: Patient inspect returns encounter and episode summary
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(*rows_per_call):
    """Return a mock client whose run_with_retry returns successive row lists."""
    client = MagicMock()
    client.close = MagicMock()
    return client


_RUN_TARGET = "libs.neo4j_client.client.run_with_retry"


def _patch_run(module_path: str, return_values: list):
    """Patch run_with_retry at the canonical import location."""
    side_effects = iter(return_values)

    def _rwr(_client, _query, **_kwargs):
        return next(side_effects, [])

    return patch(_RUN_TARGET, side_effect=_rwr)


# ---------------------------------------------------------------------------
# TC-001: Episode health
# ---------------------------------------------------------------------------


def test_episode_health_returns_status_distribution():
    """VT-089-TC-001: get_episode_health returns status counts and totals."""
    from libs.dq.episodes import get_episode_health

    mock_rows = [
        {"status": "in_progress", "auto_closed": False, "hitl_flag": False},
        {"status": "in_progress", "auto_closed": False, "hitl_flag": True},
        {"status": "stale_no_diagnosis", "auto_closed": False, "hitl_flag": False},
        {"status": "completed", "auto_closed": True, "hitl_flag": False},
    ]

    with _patch_run("libs.dq.episodes.run_with_retry", [mock_rows]):
        result = get_episode_health(MagicMock())

    assert result.total_count == 4
    assert result.status_counts["in_progress"] == 2
    assert result.status_counts["stale_no_diagnosis"] == 1
    assert result.stale_count == 1
    assert result.hitl_count == 1
    assert result.auto_closed_count == 1


def test_episode_health_empty_graph():
    """get_episode_health handles an empty graph without errors."""
    from libs.dq.episodes import get_episode_health

    with _patch_run("libs.dq.episodes.run_with_retry", [[]]):
        result = get_episode_health(MagicMock())

    assert result.total_count == 0
    assert result.stale_count == 0


# ---------------------------------------------------------------------------
# TC-002: Outcome inference
# ---------------------------------------------------------------------------


def test_infer_outcome_cancer_only():
    """VT-089-TC-002a: cancer-only signals -> INFERRED_CANCER."""
    from libs.dq.episodes import infer_outcome

    enc_rows = [
        {
            "enc_id": "e1",
            "date": "2024-02-01",
            "flags": "",
            "text": "excision booked for SCC",
        },
        {
            "enc_id": "e2",
            "date": "2024-02-15",
            "flags": "",
            "text": "oncology referral arranged",
        },
    ]

    with _patch_run("libs.dq.episodes.run_with_retry", [enc_rows]):
        result = infer_outcome(
            patient_id="p1",
            episode_id="ep1",
            site="skin",
            referral_date="2024-01-01",
            specialist_date="2024-01-20",
            client=MagicMock(),
            window_days=180,
        )

    assert result.verdict == "INFERRED_CANCER"
    assert result.flag == "INFERRED_CANCER"
    assert len(result.cancer_signals) >= 1
    assert len(result.benign_signals) == 0


def test_infer_outcome_benign_only():
    """VT-089-TC-002b: benign-only signals -> INFERRED_BENIGN."""
    from libs.dq.episodes import infer_outcome

    enc_rows = [
        {
            "enc_id": "e1",
            "date": "2024-02-01",
            "flags": "",
            "text": "discharged no further follow-up",
        },
        {
            "enc_id": "e2",
            "date": "2024-02-10",
            "flags": "",
            "text": "actinic keratosis treated with cryotherapy",
        },
    ]

    with _patch_run("libs.dq.episodes.run_with_retry", [enc_rows]):
        result = infer_outcome(
            patient_id="p1",
            episode_id="ep1",
            site="skin",
            referral_date="2024-01-01",
            specialist_date="2024-01-20",
            client=MagicMock(),
            window_days=180,
        )

    assert result.verdict == "INFERRED_BENIGN"
    assert result.flag == "INFERRED_BENIGN"
    assert len(result.benign_signals) >= 1


def test_infer_outcome_no_phase2_encounters():
    """VT-089-TC-002c: no Phase 2 encounters -> UNRESOLVABLE."""
    from libs.dq.episodes import infer_outcome

    with _patch_run("libs.dq.episodes.run_with_retry", [[]]):
        result = infer_outcome(
            patient_id="p1",
            episode_id="ep1",
            site="skin",
            referral_date="2024-01-01",
            specialist_date="2024-01-20",
            client=MagicMock(),
            window_days=180,
        )

    assert result.verdict == "UNRESOLVABLE"
    assert result.flag == "HITL_REQUIRED"
    assert result.phase2_encounter_count == 0


def test_infer_outcome_ambiguous():
    """VT-089-TC-002d: equal cancer and benign signals -> AMBIGUOUS."""
    from libs.dq.episodes import infer_outcome

    enc_rows = [
        {"enc_id": "e1", "date": "2024-02-01", "flags": "", "text": "excision booked"},
        {"enc_id": "e2", "date": "2024-02-05", "flags": "", "text": "discharged"},
    ]

    with _patch_run("libs.dq.episodes.run_with_retry", [enc_rows]):
        result = infer_outcome(
            patient_id="p1",
            episode_id="ep1",
            site="skin",
            referral_date="2024-01-01",
            specialist_date="2024-01-20",
            client=MagicMock(),
            window_days=180,
        )

    assert result.flag == "HITL_REQUIRED"


# ---------------------------------------------------------------------------
# TC-003: DQ rules engine
# ---------------------------------------------------------------------------


def test_rules_engine_returns_scorecard():
    """VT-089-TC-003: run_all_rules returns list[DQCheckResult] with >= 5 rules."""
    from libs.dq.rules_engine import run_all_rules, scorecard_summary

    # Return empty rows for all rule queries -> all pass
    def _rwr_empty(_client, _query, **_kwargs):
        return []

    with patch(_RUN_TARGET, side_effect=_rwr_empty):
        results = run_all_rules(MagicMock())

    assert len(results) >= 5
    for r in results:
        assert r.rule_id
        assert r.dimension
        assert r.severity in ("critical", "high", "medium", "low")
        assert r.status in ("pass", "warn", "fail")

    summary = scorecard_summary(results)
    assert summary["total"] == len(results)
    assert "pass" in summary


def test_rules_engine_fail_on_violations():
    """Rules with violations above threshold should report status=='fail'."""
    from libs.dq.rules_engine import _evaluate_rule

    rule = {
        "id": "TEST-001",
        "dimension": "Completeness",
        "severity": "high",
        "threshold": 0,
        "description": "Test rule",
        "cypher": "MATCH (n) RETURN n.id AS id, 'x' AS detail LIMIT 1",
    }

    def _rwr_violation(_client, _query, **_kwargs):
        return [{"id": "node-1", "detail": "x"}]

    with patch(_RUN_TARGET, side_effect=_rwr_violation):
        result = _evaluate_rule(rule, MagicMock())

    assert result.status == "fail"
    assert result.violation_count == 1


# ---------------------------------------------------------------------------
# TC-004: Remediation dry-run
# ---------------------------------------------------------------------------


def test_remediation_dry_run_no_writes():
    """VT-089-TC-004: delete_patient with dry_run=True must not call writes."""
    from libs.dq.remediation import delete_patient

    preview_rows = [{"enc_count": 5, "ep_count": 1, "doc_count": 12}]
    write_called = []

    def _rwr(client, query, **kwargs):
        if "DETACH DELETE" in query:
            write_called.append(query)
        return preview_rows if "count" in query.lower() else []

    with patch(_RUN_TARGET, side_effect=_rwr):
        result = delete_patient("p1", MagicMock(), dry_run=True)

    assert result.dry_run is True
    assert result.affected_count > 0
    assert len(write_called) == 0, "dry_run=True must not trigger DETACH DELETE"


def test_remediation_apply_calls_write():
    """delete_patient with dry_run=False must call the delete query."""
    from libs.dq.remediation import delete_patient

    calls = []

    def _rwr(client, query, **kwargs):
        calls.append(query)
        if "count" in query.lower():
            return [{"enc_count": 2, "ep_count": 1, "doc_count": 3}]
        return [{"deleted": 7}]

    with patch(_RUN_TARGET, side_effect=_rwr):
        result = delete_patient("p1", MagicMock(), dry_run=False)

    assert result.dry_run is False
    assert any(
        "DETACH DELETE" in c for c in calls
    ), "dry_run=False must run delete query"


# ---------------------------------------------------------------------------
# TC-005: Signal patterns
# ---------------------------------------------------------------------------


def test_signal_patterns_exports_required_sets():
    """VT-089-TC-005a: all four pattern sets exported and non-empty."""
    from libs.dq.signal_patterns import (
        POST_BENIGN,
        POST_CANCER,
        PRIVATE_MARKERS,
        SPECIALIST_SEEN,
    )

    assert len(POST_CANCER) > 0
    assert len(POST_BENIGN) > 0
    assert len(PRIVATE_MARKERS) > 0
    assert len(SPECIALIST_SEEN) > 0

    for pat, label in POST_CANCER:
        assert isinstance(pat, str) and len(pat) > 0
        assert isinstance(label, str) and len(label) > 0


def test_match_signals_cancer_text():
    """VT-089-TC-005b: match_signals finds cancer signal in known text."""
    from libs.dq.signal_patterns import POST_CANCER, match_signals

    hits = match_signals(
        "excision booked for confirmed SCC", POST_CANCER, date="2024-01-01"
    )
    assert len(hits) >= 1
    labels = [h.label for h in hits]
    assert any("excision" in l for l in labels)


def test_match_signals_benign_text():
    """match_signals finds benign signal in known text."""
    from libs.dq.signal_patterns import POST_BENIGN, match_signals

    hits = match_signals(
        "actinic keratosis, cryotherapy applied", POST_BENIGN, date="2024-01-01"
    )
    assert len(hits) >= 1


def test_match_signals_no_match():
    """match_signals returns empty list for text with no matching patterns."""
    from libs.dq.signal_patterns import POST_CANCER, match_signals

    hits = match_signals("routine blood pressure check", POST_CANCER, date="2024-01-01")
    assert hits == []


# ---------------------------------------------------------------------------
# TC-006: Surface form audit
# ---------------------------------------------------------------------------


def test_surface_form_audit_returns_metrics():
    """VT-089-TC-006: get_surface_form_audit returns SurfaceFormAuditResult."""
    from libs.dq.terminology import get_surface_form_audit

    mock_sf_rows = [
        {
            "normalized_term": "hypertension",
            "raw_form": "HTN",
            "edges": [
                {
                    "concept_id": "38341003",
                    "score": 0.95,
                    "active": True,
                    "source": "pinned",
                    "preferred_term": "Hypertension",
                }
            ],
            "edge_count": 1,
        },
        {
            "normalized_term": "orphan-term",
            "raw_form": "orphan",
            "edges": [],
            "edge_count": 0,
        },
        {
            "normalized_term": "dup-term",
            "raw_form": "dup",
            "edges": [
                {
                    "concept_id": "1001",
                    "score": 0.8,
                    "active": True,
                    "source": "ml",
                    "preferred_term": "A",
                },
                {
                    "concept_id": "1002",
                    "score": 0.7,
                    "active": False,
                    "source": "ml",
                    "preferred_term": "B",
                },
            ],
            "edge_count": 2,
        },
    ]

    with _patch_run("libs.dq.terminology.run_with_retry", [mock_sf_rows]):
        result = get_surface_form_audit(MagicMock(), limit=100)

    assert result.total_count == 3
    assert result.orphan_count == 1
    assert result.duplicate_count == 1
    assert result.inactive_target_count == 1


# ---------------------------------------------------------------------------
# TC-007: Patient inspect
# ---------------------------------------------------------------------------


def test_patient_summary_returns_encounter_and_episode_counts():
    """VT-089-TC-007: get_patient_summary returns correct counts."""
    from libs.dq.patient import get_patient_summary

    mock_episodes = [
        {
            "episode_id": "ep1",
            "site": "skin",
            "status": "in_progress",
            "referral_date": "2024-01-01",
            "specialist_date": None,
            "auto_closed": False,
            "hitl_flag": False,
            "hitl_reason": None,
        }
    ]
    mock_encounters = [
        {
            "encounter_id": "e1",
            "date": "2024-01-05",
            "classification": "consultation",
            "concepts": [
                {
                    "concept_id": "38341003",
                    "name": "HTN",
                    "assertion": "present",
                    "source": "ml",
                    "confidence": 0.9,
                    "semantic_tag": "disorder",
                }
            ],
            "text": "blood pressure raised",
        },
        {
            "encounter_id": "e2",
            "date": "2024-01-12",
            "classification": "document_transfer",
            "concepts": [],
            "text": None,
        },
        {
            "encounter_id": "e3",
            "date": "2024-01-20",
            "classification": "consultation",
            "concepts": [],
            "text": "skin lesion reviewed",
        },
    ]

    with _patch_run(
        "libs.dq.patient.run_with_retry",
        [mock_episodes, mock_encounters],
    ):
        summary = get_patient_summary("p1", MagicMock(), with_text=True)

    assert summary.patient_id == "p1"
    assert summary.encounter_count == 3
    assert summary.episode_count == 1
    assert summary.episodes[0].site == "skin"
    assert summary.episodes[0].status == "in_progress"
    assert summary.encounters[0].encounter_id == "e1"
