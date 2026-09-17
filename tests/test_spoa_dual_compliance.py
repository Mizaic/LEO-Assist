"""Tests for dual compliance evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline_graph.subgraphs.compliance import (
    _evaluate_dual_compliance,
    _patient_eval_kwargs,
    evaluate_compliance,
)


def test_patient_eval_passes_letter_text_from_encounter() -> None:
    kwargs = _patient_eval_kwargs(
        {"encounter_text": "chronic recurrent vaginal discharge"},
        [],
        "guideline",
        "NG12",
        "NG12",
    )
    assert kwargs["letter_text"] == "chronic recurrent vaginal discharge"


def test_patient_eval_forwards_concept_occurrences_and_historical() -> None:
    kwargs = _patient_eval_kwargs(
        {
            "encounter_text": "old fracture",
            "entities": [
                {
                    "concept_id": "66308002",
                    "assertion": "historical",
                    "observed_at": "2019-03-12",
                    "label": "disorder",
                }
            ],
        },
        [],
        "guideline",
        "NG12",
        "NG12",
    )
    assert "66308002" in kwargs["historical_concept_ids"]
    assert kwargs["concept_occurrences"]["66308002"][0].year == 2019


def _rule(rule_id: str, guideline_id: str) -> dict:
    return {
        "rule_id": rule_id,
        "guideline_id": guideline_id,
        "name": f"Rule {rule_id}",
        "actions": [{"priority": "2ww", "name": "Chest X-ray"}],
    }


@patch("libs.pipeline_graph.subgraphs.compliance._run_patient_eval")
def test_primary_miss_runs_alternative_scan(mock_run: MagicMock) -> None:
    def _evaluate(codes, kwargs):
        pathway_filter = kwargs.get("pathway_filter")
        if pathway_filter == "NG12":
            return {"matched_rules": []}, False
        return {"matched_rules": [_rule("alt-1", "NG27")]}, False

    mock_run.side_effect = _evaluate
    state = {
        "primary_guideline_ids": ["NG12"],
        "healthcare_service_id": "6711368",
        "healthcare_service_name": "Fast track cancer referral",
        "healthcare_service_specialty": "2WW",
    }
    result = _evaluate_dual_compliance(state, ["123"])
    assert result["matched_rules"] == []
    assert result["primary"]["supported"] is False
    assert len(result["alternatives"]["matched_rules"]) == 1
    assert result["alternatives"]["matched_rules"][0]["rule_id"] == "alt-1"


@patch("libs.pipeline_graph.subgraphs.compliance._run_patient_eval")
def test_offer_only_primary_hit_is_not_supported(mock_run: MagicMock) -> None:
    mock_run.return_value = (
        {
            "matched_rules": [
                {
                    "rule_id": "1.10.4",
                    "guideline_id": "NG12",
                    "name": "Rule: 1.10.4",
                    "strength": "offer",
                    "actions": [{"priority": "routine", "name": "Full blood count"}],
                }
            ]
        },
        False,
    )
    state = {"primary_guideline_ids": ["NG12"]}
    result = _evaluate_dual_compliance(state, ["66308002"])
    assert result["primary"]["supported"] is False
    assert result["is_compliant"] is False
    assert result["matched_rules"][0]["rule_id"] == "1.10.4"


@patch("libs.pipeline_graph.subgraphs.compliance._run_patient_eval")
def test_primary_hit_keeps_top_level_matches(mock_run: MagicMock) -> None:
    mock_run.return_value = ({"matched_rules": [_rule("pri-1", "NG12")]}, False)
    state = {"primary_guideline_ids": ["NG12"]}
    result = _evaluate_dual_compliance(state, ["123"])
    assert result["matched_rules"][0]["rule_id"] == "pri-1"
    assert result["primary"]["supported"] is True
    assert result["alternatives"]["matched_rules"] == []


@patch(
    "libs.pipeline_graph.subgraphs.compliance._evaluate_dual_compliance",
    autospec=True,
)
def test_evaluate_compliance_returns_structured_payload(mock_dual: MagicMock) -> None:
    mock_dual.return_value = {
        "matched_rules": [],
        "primary": {"supported": False, "matched_rules": []},
        "alternatives": {"matched_rules": [_rule("alt-1", "NG27")]},
        "healthcare_service_missing": False,
        "is_compliant": False,
    }
    payload = evaluate_compliance(
        {
            "patient_id": "p1",
            "entities": [],
            "referral_reason": "Suspected breast lump",
        }
    )
    assert payload["compliance_result"]["alternatives"]["matched_rules"]


@patch("libs.pipeline_graph.subgraphs.compliance._evaluate_dual_compliance")
def test_unscored_form_with_extracted_reason_still_evaluates_guidelines(
    mock_dual: MagicMock,
) -> None:
    mock_dual.return_value = {
        "matched_rules": [],
        "primary": {"supported": False, "matched_rules": []},
        "alternatives": {"matched_rules": []},
        "is_compliant": False,
    }
    evaluate_compliance(
        {
            "patient_id": "p1",
            "referral_reason": "Right breast pain after implant rupture",
            "entities": [
                {
                    "concept_id": "29857009",
                    "assertion": "present",
                    "label": "finding",
                    "text": "right-sided breast pain",
                }
            ],
            "completeness_result": {
                "complete": False,
                "degraded": True,
                "missing_groups": [
                    {
                        "name": "two_ww_criterion_required",
                        "required": True,
                        "outcome": "not_assessable",
                    }
                ],
            },
        }
    )
    mock_dual.assert_called_once()


@patch("libs.pipeline_graph.subgraphs.compliance._evaluate_dual_compliance")
def test_few_shot_finding_is_enough_reason_to_evaluate(
    mock_dual: MagicMock,
) -> None:
    mock_dual.return_value = {
        "matched_rules": [],
        "primary": {"supported": False, "matched_rules": []},
        "alternatives": {"matched_rules": []},
        "is_compliant": False,
    }
    evaluate_compliance(
        {
            "patient_id": "p1",
            "referral_reason": "",
            "entities": [
                {
                    "assertion": "present",
                    "label": "finding",
                    "text": "right-sided breast pain",
                }
            ],
        }
    )
    mock_dual.assert_called_once()


@patch("libs.pipeline_graph.subgraphs.compliance._evaluate_dual_compliance")
def test_missing_reason_does_not_fire_guideline_rules(mock_dual: MagicMock) -> None:
    payload = evaluate_compliance(
        {
            "patient_id": "p1",
            "referral_reason": "",
            "entities": [],
            "section_hits": [],
        }
    )
    mock_dual.assert_not_called()
    result = payload["compliance_result"]
    assert result["matched_rules"] == []
    assert result["primary"]["supported"] is False
    assert result["missing_referral_reason"] is True
