"""Tests for the persistent test-patient library -- VT-LEO-AI-164.

Covers:
  - PatientPayload.content_hash is deterministic and order-insensitive.
  - dry_run merges terminology eval results with branch-path walking.
  - confirm_and_save is idempotent on duplicate content_hash.
  - diff_replay correctly buckets passes / regressions / unexpected.
  - replay_scope persists a report when persist_report=True.
  - Demographic / NOT / AT_LEAST evaluation in _walk_satisfied.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services import test_patient_service as svc
from app.services.test_patient_service import (
    PatientPayload,
    diff_replay,
    _check_demographic,
    _walk_satisfied,
)


# -- PatientPayload --------------------------------------------------------


def test_content_hash_order_independent() -> None:
    a = PatientPayload(codes=["123", "456"], age=70, sex="male")
    b = PatientPayload(codes=["456", "123"], age=70, sex="MALE")
    assert a.content_hash() == b.content_hash()


def test_content_hash_changes_with_demographics() -> None:
    a = PatientPayload(codes=["1"], age=70, sex="male")
    b = PatientPayload(codes=["1"], age=71, sex="male")
    assert a.content_hash() != b.content_hash()


def test_content_hash_strips_whitespace_and_dedups() -> None:
    a = PatientPayload(codes=["1", " 1 ", ""])
    b = PatientPayload(codes=["1"])
    assert a.content_hash() == b.content_hash()


# -- _walk_satisfied -------------------------------------------------------


def _concept(node_id: str, cid: str) -> dict:
    return {
        "node_id": node_id,
        "kind": "CONCEPT",
        "criterion": {"snomed_concept_id": cid},
    }


def test_walk_satisfied_simple_and() -> None:
    tree = {
        "node_id": "root",
        "kind": "AND",
        "children": [_concept("c1", "100"), _concept("c2", "200")],
    }
    acc: list[str] = []
    assert _walk_satisfied(tree, {"100", "200"}, None, None, acc) is True
    assert "root" in acc and "c1" in acc and "c2" in acc

    acc2: list[str] = []
    assert _walk_satisfied(tree, {"100"}, None, None, acc2) is False


def test_walk_satisfied_at_least_min_2() -> None:
    tree = {
        "node_id": "root",
        "kind": "AT_LEAST",
        "min": 2,
        "children": [
            _concept("a", "1"),
            _concept("b", "2"),
            _concept("c", "3"),
        ],
    }
    assert _walk_satisfied(tree, {"1", "2"}, None, None, []) is True
    assert _walk_satisfied(tree, {"1"}, None, None, []) is False


def test_walk_satisfied_not_inverts() -> None:
    tree = {
        "node_id": "root",
        "kind": "NOT",
        "children": [_concept("inner", "999")],
    }
    assert _walk_satisfied(tree, {"999"}, None, None, []) is False
    assert _walk_satisfied(tree, set(), None, None, []) is True


def test_check_demographic_age_and_sex() -> None:
    assert _check_demographic(
        {"field": "age", "operator": ">=", "value": 65}, 70, None
    )
    assert not _check_demographic(
        {"field": "age", "operator": ">=", "value": 65}, 60, None
    )
    assert _check_demographic(
        {"field": "sex", "operator": "==", "value": "male"}, None, "MALE"
    )
    assert not _check_demographic(
        {"field": "age", "operator": ">", "value": 65}, None, None
    )


# -- dry_run ---------------------------------------------------------------


def test_dry_run_returns_branch_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """dry_run should walk each matched rule's tree to produce branch_paths."""
    rule = {
        "rule_id": "r1",
        "guideline_id": "g1",
        "logic_json": json.dumps(
            {"node_id": "root", "kind": "AND", "children": [_concept("c1", "100")]}
        ),
    }

    def fake_eval(payload, **kwargs):  # noqa: ARG001 - test stub
        return {
            "matched_rules": [{"rule_id": "r1", "name": "Rule 1"}],
            "version": "v42",
        }

    monkeypatch.setattr(svc, "evaluate_against_terminology", fake_eval)

    client = MagicMock()
    client.run.return_value = [rule]

    result = svc.dry_run(client, PatientPayload(codes=["100"]))
    assert result["matched_rules"] == [{"rule_id": "r1", "name": "Rule 1"}]
    assert result["branch_paths"]["r1"] == ["c1", "root"] or set(
        result["branch_paths"]["r1"]
    ) == {"c1", "root"}
    assert result["ruleset_version"] == "v42"


def test_dry_run_handles_eval_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(payload, **kwargs):  # noqa: ARG001
        raise RuntimeError("terminology api offline")

    monkeypatch.setattr(svc, "evaluate_against_terminology", boom)
    client = MagicMock()
    with pytest.raises(RuntimeError, match="terminology api offline"):
        svc.dry_run(client, PatientPayload(codes=["100"]))


# -- confirm_and_save ------------------------------------------------------


def test_confirm_and_save_skips_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "find_existing", lambda *a, **k: "tp_existing")
    client = MagicMock()
    payload = PatientPayload(codes=["1"], age=70, sex="male")
    result = svc.confirm_and_save(
        client,
        payload,
        [{"rule_id": "r1", "fires": True}],
        guideline_id="g1",
        scope_type="global",
        scope_id="default",
        created_by="user@test",
    )
    assert result == {
        "id": "tp_existing",
        "created": False,
        "expectations_written": 0,
        "reason": "duplicate",
    }
    client.run.assert_not_called()


def test_confirm_and_save_creates_and_writes_expectations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc, "find_existing", lambda *a, **k: None)
    client = MagicMock()
    payload = PatientPayload(codes=["1"], age=70, sex="male")
    result = svc.confirm_and_save(
        client,
        payload,
        [
            {"rule_id": "r1", "fires": True, "matched_branch_node_ids": ["n1"]},
            {"rule_id": "r2", "fires": False},
            {"rule_id": "", "fires": True},  # ignored - no rule_id
        ],
        guideline_id="g1",
        scope_type="global",
        scope_id="default",
        created_by="user@test",
        ruleset_version="v1",
    )
    assert result["created"] is True
    assert result["expectations_written"] == 2
    assert result["id"].startswith("tp_")
    # 1 create + 2 expectation writes
    assert client.run.call_count == 3


# -- update_patient --------------------------------------------------------


def test_update_patient_rewrites_profile_and_expectations() -> None:
    """Happy path: UPDATE_TEST_PATIENT then one WRITE_EXPECTED_RESULT
    per kept expectation (rule_id-less entries are dropped, matching
    the create flow)."""
    client = MagicMock()
    # First call (UPDATE) returns one row -> patient exists.
    client.run.side_effect = [
        [{"id": "tp_existing"}],
        [{"rule_id": "r1"}],
        [{"rule_id": "r2"}],
    ]
    payload = PatientPayload(
        codes=["100", "200"], age=71, sex="female", name="Edited"
    )
    result = svc.update_patient(
        client,
        patient_id="tp_existing",
        payload=payload,
        expectations=[
            {"rule_id": "r1", "fires": True, "matched_branch_node_ids": ["n1"]},
            {"rule_id": "r2", "fires": False},
            {"rule_id": "", "fires": True},  # dropped
        ],
        updated_by="user@test",
        ruleset_version="v2",
    )
    assert result == {
        "id": "tp_existing",
        "updated": True,
        "expectations_written": 2,
    }
    # 1 UPDATE + 2 WRITE_EXPECTED_RESULT calls.
    assert client.run.call_count == 3
    # First call is the UPDATE_TEST_PATIENT cypher with the new
    # profile values + the patient_id from the URL.
    update_call_kwargs = client.run.call_args_list[0].kwargs
    assert update_call_kwargs["id"] == "tp_existing"
    assert update_call_kwargs["codes"] == ["100", "200"]
    assert update_call_kwargs["age"] == 71
    assert update_call_kwargs["sex"] == "female"
    assert update_call_kwargs["name"] == "Edited"
    assert update_call_kwargs["updated_by"] == "user@test"
    # content_hash recomputed from the new payload.
    assert update_call_kwargs["content_hash"] == payload.content_hash()


def test_update_patient_404_when_match_returns_no_rows() -> None:
    """When the Cypher MATCH finds nothing (no patient with that id)
    the service must return updated=False and skip the expectation
    writes -- the router translates updated=False into HTTP 404."""
    client = MagicMock()
    client.run.return_value = []
    payload = PatientPayload(codes=["1"], age=70, sex="male")
    result = svc.update_patient(
        client,
        patient_id="tp_missing",
        payload=payload,
        expectations=[{"rule_id": "r1", "fires": True}],
        updated_by="user@test",
    )
    assert result == {
        "id": "tp_missing",
        "updated": False,
        "expectations_written": 0,
    }
    # No expectation writes happened because the patient does not exist.
    assert client.run.call_count == 1


def test_update_patient_clears_expectations_when_list_is_empty() -> None:
    """Editing a patient down to zero expectations is allowed; the
    UPDATE Cypher already DELETEs the existing rels, so we just don't
    call WRITE_EXPECTED_RESULT at all."""
    client = MagicMock()
    client.run.return_value = [{"id": "tp_existing"}]
    payload = PatientPayload(codes=["1"], age=70, sex="male")
    result = svc.update_patient(
        client,
        patient_id="tp_existing",
        payload=payload,
        expectations=[],
        updated_by="user@test",
    )
    assert result == {
        "id": "tp_existing",
        "updated": True,
        "expectations_written": 0,
    }
    # Only the UPDATE call ran; no WRITE_EXPECTED_RESULT writes.
    assert client.run.call_count == 1


# -- diff_replay -----------------------------------------------------------


def test_diff_replay_buckets_pass_regression_unexpected() -> None:
    expectations = [
        {"rule_id": "r1", "fires": True},
        {"rule_id": "r2", "fires": False},
        {"rule_id": "r3", "fires": True},
    ]
    current = [
        {"rule_id": "r1", "name": "Rule 1"},  # passes - expected fires
        {"rule_id": "r2", "name": "Rule 2"},  # regression - expected NOT fires
        {"rule_id": "r4", "name": "Rule 4"},  # unexpected match
    ]
    diff = diff_replay(expectations, current)
    assert {p["rule_id"] for p in diff["passes"]} == {"r1"}
    assert {r["rule_id"] for r in diff["regressions"]} == {"r2", "r3"}
    assert [u["rule_id"] for u in diff["unexpected_matches"]] == ["r4"]
    assert diff["total_assertions"] == 3


# -- replay_scope ----------------------------------------------------------


def test_replay_scope_persists_report(monkeypatch: pytest.MonkeyPatch) -> None:
    patient = {
        "id": "tp1",
        "name": "P1",
        "codes": ["100"],
        "age": 70,
        "sex": "male",
        "expectations": [{"rule_id": "r1", "fires": True}],
    }
    monkeypatch.setattr(svc, "list_patients", lambda *a, **k: [patient])
    monkeypatch.setattr(
        svc,
        "evaluate_against_terminology",
        lambda payload, **k: {"matched_rules": [{"rule_id": "r1"}]},
    )

    persisted: dict = {}

    def fake_persist(client, report):  # noqa: ARG001
        persisted.update(report)
        return "rv_test"

    monkeypatch.setattr(svc, "_persist_replay_report", fake_persist)

    client = MagicMock()
    report = svc.replay_scope(
        client, guideline_id="g1", ruleset_version="v1"
    )
    assert report["id"] == "rv_test"
    assert report["passes_count"] == 1
    assert report["regressions_count"] == 0
    assert report["patient_count"] == 1
    assert persisted["ruleset_version"] == "v1"


def test_replay_scope_skips_persist_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc, "list_patients", lambda *a, **k: [])
    called: dict = {"persisted": False}

    def fake_persist(*a, **k):  # noqa: ARG001
        called["persisted"] = True
        return "rv"

    monkeypatch.setattr(svc, "_persist_replay_report", fake_persist)

    report = svc.replay_scope(
        MagicMock(), guideline_id="g1", persist_report=False
    )
    assert "id" not in report
    assert called["persisted"] is False
