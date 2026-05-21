"""API validation term aliases for phrase-level F1."""

from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[1] / "services" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from libs.validation.extraction_phrase_scoring import (  # noqa: E402
    build_case_alias_map,
    normalise_validation_term,
    normalise_validation_terms,
)


def test_phrase_alias_mri_and_ca125() -> None:
    case = {"expected_observables": []}
    out_entities = normalise_validation_terms(
        [
            {"text": "MRI scan of the brain", "semantic_tag": "procedure"},
            {
                "text": "CA125 level is raised at 92 U/mL",
                "semantic_tag": "observable_entity",
            },
            {"text": "Glycated haemoglobin", "semantic_tag": "observable_entity"},
            {"text": "Plasma viscosity", "semantic_tag": "observable_entity"},
        ],
        case,
    )
    out = [e["text"] for e in out_entities]
    assert "urgent MRI scan of the brain" in out
    assert "CA125 raised" in out
    assert "HbA1c" in out
    assert "PV" in out


def test_routing_phrase_dropped_by_noise_markers() -> None:
    alias_map = build_case_alias_map(None)
    assert (
        normalise_validation_term(
            "referral criteria and clinical information", alias_map
        )
        == ""
    )


def test_gold_substring_shortens_long_model_span() -> None:
    case = {
        "expected_strings": [
            {"text": "visual disturbance", "semantic_tag": "disorder"},
            {"text": "abnormal MRI", "semantic_tag": "finding"},
        ]
    }
    alias_map = build_case_alias_map(case)
    assert (
        normalise_validation_term(
            "new onset visual disturbance in the right field",
            alias_map,
            case,
        )
        == "visual disturbance"
    )
    assert (
        normalise_validation_term("abnormal MRI brain scan", alias_map, case)
        == "abnormal MRI"
    )


def test_clinical_finding_tags_match_across_families() -> None:
    from tests.helpers.clinical_extraction_scenario_loader import score_case

    case = {
        "case_id": "tag-family",
        "expected_strings": [
            {"text": "bilateral papilloedema", "semantic_tag": "disorder"}
        ],
        "expected_observables": [],
    }
    extracted = [{"text": "bilateral papilloedema", "semantic_tag": "finding"}]
    rules = {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
        "containment_match": True,
    }
    assert score_case(case, extracted, rules)["f1"] == 1.0


def test_fasting_glucose_is_kept_as_observable() -> None:
    case = {"expected_strings": []}
    out = normalise_validation_terms(
        [{"text": "Fasting glucose", "semantic_tag": "observable_entity"}],
        case,
    )
    assert out == [{"text": "Fasting glucose", "semantic_tag": "observable_entity"}]


def test_exact_text_tag_mismatch_is_not_hidden() -> None:
    case = {
        "expected_strings": [{"text": "abnormal MRI", "semantic_tag": "finding"}],
    }
    out = normalise_validation_terms(
        [{"text": "abnormal MRI", "semantic_tag": "procedure"}],
        case,
    )
    assert out == [{"text": "abnormal MRI", "semantic_tag": "procedure"}]
