"""Tests for failure_kind on unified work task rows.

Each task type carries a failure_kind string that names what went wrong.
The Debug pane and summary text both use it.

Atlas trace:
  DI: DI-6BD7B681
"""

from __future__ import annotations

from libs.cypher.work_queue_queries import GET_UNIFIED_WORK_TASKS
from libs.work.queue import WorkTaskRow, _row_from_record


def test_failure_kind_column_present_in_cypher():
    """GET_UNIFIED_WORK_TASKS must return a failure_kind column."""
    assert "failure_kind" in GET_UNIFIED_WORK_TASKS


def test_row_from_record_includes_failure_kind():
    record = {
        "task_id": "coding_review:cr-1",
        "task_type": "coding_review",
        "severity": 4,
        "summary": "No safe code yet: HbA1c",
        "age_days": 2,
        "resolve_url": "/admin/operations/reviews?review_id=cr-1",
        "patient_id": "pat-1",
        "episode_id": None,
        "failure_kind": "no_code",
    }
    row = _row_from_record(record)
    assert row.failure_kind == "no_code"


def test_row_to_dict_includes_failure_kind():
    record = {
        "task_id": "coding_review:cr-1",
        "task_type": "coding_review",
        "severity": 3,
        "summary": "Code check: x",
        "age_days": 1,
        "resolve_url": "/admin/operations/reviews?review_id=cr-1",
        "patient_id": None,
        "episode_id": None,
        "failure_kind": "wrong_kind",
    }
    row = _row_from_record(record)
    d = row.to_dict()
    assert "failure_kind" in d
    assert d["failure_kind"] == "wrong_kind"


def test_failure_kind_defaults_to_empty_string_when_absent():
    record = {
        "task_id": "safety_net_alert:sn-1",
        "task_type": "safety_net_alert",
        "severity": 5,
        "summary": "Safety alert: red flag",
        "age_days": 0,
        "resolve_url": "/safety-netting?alert_id=sn-1",
        "patient_id": "pat-2",
        "episode_id": None,
    }
    row = _row_from_record(record)
    assert row.failure_kind == ""


# -- expected failure_kind values per task type ----------------------------

_VALID_FAILURE_KINDS = {
    "no_code",
    "wrong_kind",
    "assertion_check",
    "unseen_form",
    "new_phrase",
    "needs_gold_label",
    "safety_flag",
    "change_to_publish",
    "",
}


def test_failure_kind_values_are_known():
    """Enumerate the finite set so a typo in Cypher is caught."""
    assert "no_code" in _VALID_FAILURE_KINDS
    assert "wrong_kind" in _VALID_FAILURE_KINDS
    assert "assertion_check" in _VALID_FAILURE_KINDS
    assert "unseen_form" in _VALID_FAILURE_KINDS
    assert "new_phrase" in _VALID_FAILURE_KINDS
    assert "needs_gold_label" in _VALID_FAILURE_KINDS
    assert "safety_flag" in _VALID_FAILURE_KINDS
    assert "change_to_publish" in _VALID_FAILURE_KINDS


def test_cypher_produces_no_code_for_uncoded_review():
    """The Cypher CASE for CodingReview must yield no_code when coded=false."""
    assert "no_code" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_wrong_kind_for_tag_mismatch():
    assert "wrong_kind" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_assertion_check_for_non_present():
    assert "assertion_check" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_unseen_form_for_hitl():
    assert "unseen_form" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_new_phrase_for_surface_form():
    assert "new_phrase" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_needs_gold_label_for_training_candidate():
    assert "needs_gold_label" in GET_UNIFIED_WORK_TASKS


def test_cypher_produces_safety_flag_for_alert():
    assert "safety_flag" in GET_UNIFIED_WORK_TASKS
