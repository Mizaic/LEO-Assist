"""Tests for compliance stage_summary and guideline_diagnostics (Validation Lab)."""

from __future__ import annotations

from typing import Any


def test_build_stage_summary_includes_scope_and_codes():
    from libs.pipeline_graph.subgraphs.compliance_diagnostics import build_stage_summary

    summary = build_stage_summary(
        {
            "guideline_scope_id": "NG12",
            "guideline_ruleset_version": "v-test",
            "patient_age": 62,
            "patient_sex": "male",
        },
        codes=["123", "456"],
        entities=[
            {"concept_id": "123", "text": "Dysphagia"},
            {"text": "uncoded"},
        ],
        result={
            "matched_rules": [{"rule_id": "NG12:1.3.1", "name": "Urgent referral"}],
            "is_compliant": True,
            "active_version": "v-live",
        },
    )

    assert summary["subgraph_id"] == "compliance"
    assert "NG12" in summary["headline"]
    assert summary["inputs"]["evaluated_codes"] == ["123", "456"]
    assert summary["outputs"]["matched_rule_count"] == 1
    assert summary["outputs"]["matched_rule_ids"] == ["NG12:1.3.1"]


def test_build_guideline_diagnostics_skipped_without_lab_flag():
    from libs.pipeline_graph.subgraphs.compliance_diagnostics import (
        build_guideline_diagnostics,
    )

    class _FakeEvaluator:
        def diagnose(self, *_args, **_kwargs):
            raise AssertionError("diagnose should not run")

    assert build_guideline_diagnostics(_FakeEvaluator(), {}, codes=[], result={}) == {}


def test_build_guideline_diagnostics_runs_for_matched_rules(monkeypatch):
    from libs.pipeline_graph.subgraphs.compliance_diagnostics import (
        build_guideline_diagnostics,
    )

    class _FakeEvaluator:
        def _load_ruleset(self, *_args, **_kwargs):
            return {
                "rules": [
                    {"rule_id": "NG12:1.3.1", "guideline_id": "NG12"},
                    {"rule_id": "NG12:9.9.9", "guideline_id": "NG12"},
                ]
            }

        def diagnose(self, rule_id, _codes, **_kwargs):
            fires = rule_id == "NG12:1.3.1"
            return {
                "rule_id": rule_id,
                "rule_name": rule_id,
                "guideline_id": "NG12",
                "fires": fires,
                "annotated_tree": {
                    "kind": "AND",
                    "matched": fires,
                    "children": [
                        {"kind": "CONCEPT", "matched": True},
                        {"kind": "CONCEPT", "matched": fires},
                    ],
                },
            }

    state = {
        "capture_validation_output": True,
        "guideline_scope_id": "NG12",
    }
    result = {
        "matched_rules": [{"rule_id": "NG12:1.3.1"}],
    }
    diag = build_guideline_diagnostics(
        _FakeEvaluator(), state, codes=["1"], result=result
    )

    assert len(diag["matched"]) == 1
    assert diag["matched"][0]["fires"] is True
    assert len(diag["near_miss"]) == 1
    assert diag["near_miss"][0]["rule_id"] == "NG12:9.9.9"
    assert diag["near_miss"][0]["match_ratio"] == 0.5


def test_evaluate_compliance_emits_stage_summary(monkeypatch):
    from libs.pipeline_graph.subgraphs import compliance

    monkeypatch.setattr(
        compliance,
        "_evaluate_guideline",
        lambda _state, codes: {
            "matched_rules": [],
            "is_compliant": False,
            "active_version": "v1",
        },
    )

    result = compliance.evaluate_compliance(
        {
            "patient_id": "p1",
            "guideline_scope_id": "NG12",
            "entities": [{"concept_id": "999"}],
        }
    )

    assert result["stage_summary"]["inputs"]["guideline_scope_id"] == "NG12"
    assert "guideline_diagnostics" not in result


def test_evaluate_compliance_emits_guideline_diagnostics_in_lab(monkeypatch):
    from libs.pipeline_graph.subgraphs import compliance

    monkeypatch.setattr(
        compliance,
        "_evaluate_guideline",
        lambda _state, _codes: {
            "matched_rules": [{"rule_id": "NG12:1.1"}],
            "is_compliant": True,
        },
    )
    monkeypatch.setattr(
        compliance,
        "_guideline_evaluator",
        lambda: object(),
    )
    monkeypatch.setattr(
        compliance,
        "build_guideline_diagnostics",
        lambda *_args, **_kwargs: {
            "matched": [{"rule_id": "NG12:1.1"}],
            "near_miss": [],
        },
    )

    result = compliance.evaluate_compliance(
        {
            "patient_id": "p1",
            "guideline_scope_id": "NG12",
            "capture_validation_output": True,
            "entities": [{"concept_id": "111"}],
        }
    )

    assert result["guideline_diagnostics"]["matched"][0]["rule_id"] == "NG12:1.1"
