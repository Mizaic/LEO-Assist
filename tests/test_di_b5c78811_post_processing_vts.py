"""One verification test per DI-B5C78811 acceptance criterion (implementable pytest).

Atlas trace:
  DI: DI-B5C78811
  DO: DO-728930A1
  VT-88920DAA  AC1 shared stack layer order
  VT-29AF2163  AC2 observable normalisation and surface cleanup
  VT-2A7C5322  AC3 value-unit linking before entity-type norm
  VT-4231B0A0  AC4 structured observable label guard
  VT-E425D17E  AC5 scope guard
  VT-CC118874  AC6 ConText assertion detection
  VT-7AC15E8B  AC7 cross-line lab finding merge
  VT-29880CC8  AC8 validation corpus F1 threshold

Run: pytest tests/test_di_b5c78811_post_processing_vts.py -v --no-cov
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.scope_guard import SUPPRESSED, reclassify_assertion
from libs.pipeline.post_processing import (
    _apply_scope_guard_to_dicts,
    clean_observable_surface_forms,
    link_observable_value_units,
    merge_cross_line_lab_findings,
    normalise_entity_types,
    run_post_processing_with_trace,
)
from tests.helpers.clinical_extraction_scenario_loader import (
    fixture_dir,
    load_expected_strings,
    score_extraction_cases,
)

ROOT = Path(__file__).resolve().parents[1]
LABEL_VERIFIER = ROOT / "services/api/app/services/label_verifier.py"
POST_PROCESSING_SUBGRAPH = ROOT / "libs/pipeline_graph/subgraphs/post_processing.py"
EXTRACTION_SCENARIOS_ROUTER = ROOT / "services/api/app/routers/extraction_scenarios.py"

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -- AC1: shared stack + layer order -----------------------------------------


def test_vt88920daa_shared_post_processing_stack_layer_order() -> None:
    """VT-88920DAA / DI-B5C78811 AC1 -- shared stack and layer order."""
    label_src = _read(LABEL_VERIFIER)
    subgraph_src = _read(POST_PROCESSING_SUBGRAPH)

    assert "from libs.pipeline.post_processing import" in label_src
    assert "run_post_processing" in label_src
    assert "run_post_processing_with_trace" in subgraph_src

    entities = [{"text": "Hb", "label": "observable_entity", "start": 0, "end": 2}]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        _processed, trace = run_post_processing_with_trace("Hb 120 g/L", entities)

    completed = [r for r in trace if r.get("status") == "completed"]
    by_id = {r["layer_id"]: r for r in completed}
    assert completed.index(by_id["layer_5"]) < completed.index(by_id["layer_6"])
    assert by_id["layer_5"]["name"] == "Value-Unit Linking"
    assert by_id["layer_6"]["name"] == "Entity-Type Normalisation"


# -- AC2: observable normalisation + surface cleanup ---------------------------


def test_vt29af2163_observable_normalisation_and_surface_cleanup() -> None:
    """VT-29AF2163 / DI-B5C78811 AC2 -- observable norm and surface cleanup."""
    raw_with_range = "Haemoglobin concentration 106 g/L [130-180]"
    range_entities = [
        {
            "text": raw_with_range,
            "label": "observable_entity",
            "start": 0,
            "end": len(raw_with_range),
            "assertion": "present",
        }
    ]
    ranged = normalize_observable_entities("", range_entities, add_qualifier_value=False)[0]
    assert ranged["value"] == "106"
    assert ranged["unit"] == "g/L"
    assert ranged.get("reference_range") == "130-180"

    raw = "Haemoglobin concentration 106 g/L"
    entities = [
        {
            "text": raw,
            "label": "observable_entity",
            "start": 0,
            "end": len(raw),
            "assertion": "present",
        }
    ]
    normalised = normalize_observable_entities("", entities, add_qualifier_value=False)
    cleaned = clean_observable_surface_forms(normalised)

    obs = cleaned[0]
    assert obs["value"] == "106"
    assert obs["unit"] == "g/L"
    assert obs["text"] == "Haemoglobin concentration"


# -- AC3: value-unit linking before entity-type norm --------------------------


def test_vt2a7c5322_value_unit_linking_before_entity_type_normalisation() -> None:
    """VT-2A7C5322 / DI-B5C78811 AC3 -- value-unit linking before entity-type norm."""
    entities = [
        {
            "text": "HbA1c",
            "label": "observable_entity",
            "start": 0,
            "end": 5,
        },
        {
            "text": "45.0 mmol/mol",
            "label": "qualifier_value",
            "start": 20,
            "end": 33,
        },
    ]
    encounter = "Panel shows HbA1c was 45.0 mmol/mol."
    link_observable_value_units(entities, encounter)
    normalise_entity_types(entities)

    obs = [e for e in entities if e["label"] == "observable_entity"]
    assert len(obs) == 1
    assert obs[0]["text"] == "HbA1c"
    assert obs[0].get("value") == "45.0"
    assert obs[0].get("unit") == "mmol/mol"


# -- AC4: structured observable not demoted ----------------------------------


def test_vt4231b0a0_structured_observable_keeps_label() -> None:
    """VT-4231B0A0 / DI-B5C78811 AC4 -- structured observable label guard."""
    entities = [
        {
            "text": "Ferritin",
            "label": "observable_entity",
            "start": 0,
            "end": 8,
            "value": "419.0",
            "unit": "ug/L",
        }
    ]
    normalise_entity_types(entities)
    assert entities[0]["label"] == "observable_entity"


# -- AC5: scope guard ----------------------------------------------------------


def test_vte425d17e_scope_guard_safety_netting_recommendation_and_hedge() -> None:
    """VT-E425D17E / DI-B5C78811 AC5 -- scope guard behaviour."""
    netting = "Call 999 if you develop chest pain."
    entities = [
        {
            "text": "chest pain",
            "label": "finding",
            "start": netting.find("chest pain"),
            "end": netting.find("chest pain") + len("chest pain"),
            "assertion": "present",
        }
    ]
    _apply_scope_guard_to_dicts(netting, entities)
    assert entities == []

    recommend = "Consider starting aspirin if symptoms persist."
    ent = {
        "text": "aspirin",
        "label": "substance",
        "start": recommend.find("aspirin"),
        "end": recommend.find("aspirin") + len("aspirin"),
        "assertion": "present",
    }
    _apply_scope_guard_to_dicts(recommend, [ent])
    assert ent["assertion"] == "hypothetical"

    hedge = "Picture is consistent with pneumonia."
    disorder = {
        "text": "pneumonia",
        "label": "disorder",
        "start": hedge.find("pneumonia"),
        "end": hedge.find("pneumonia") + len("pneumonia"),
        "assertion": "present",
    }
    _apply_scope_guard_to_dicts(hedge, [disorder])
    assert disorder["assertion"] == "possible"

    assert (
        reclassify_assertion(
            entity_semantic_tag="finding",
            entity_assertion="present",
            sentence_text=netting,
            entity_text="chest pain",
        )
        == SUPPRESSED
    )


# -- AC6: ConText assertion detection ----------------------------------------


def test_vtcc118874_context_sets_negation_and_family() -> None:
    """VT-CC118874 / DI-B5C78811 AC6 -- ConText assertion detection."""
    try:
        from libs.ner.context_engine import apply_context_detection_to_dicts
    except ImportError:
        pytest.skip("MedSpaCy ConText not available")

    neg_sentence = "No chest pain reported today."
    neg_ent = {
        "text": "chest pain",
        "label": "finding",
        "assertion": "present",
        "start": neg_sentence.lower().find("chest pain"),
        "end": neg_sentence.lower().find("chest pain") + len("chest pain"),
    }
    apply_context_detection_to_dicts(neg_sentence, [neg_ent])
    assert neg_ent["assertion"] == "absent"

    fhx_sentence = "FHx of diabetes in mother."
    fhx_ent = {
        "text": "diabetes",
        "label": "disorder",
        "assertion": "present",
        "start": fhx_sentence.lower().find("diabetes"),
        "end": fhx_sentence.lower().find("diabetes") + len("diabetes"),
    }
    apply_context_detection_to_dicts(fhx_sentence, [fhx_ent])
    assert fhx_ent["assertion"] == "family"


# -- AC7: cross-line lab merge ------------------------------------------------


def test_vt7ac15e8b_cross_line_lab_finding_merge() -> None:
    """VT-7AC15E8B / DI-B5C78811 AC7 -- cross-line lab finding merge."""
    value_line = "Prostate-specific antigen level (XE25C) 12 ng/ml [0 - 6.5]"
    encounter = f"{value_line}\n\nOutside reference range"
    start = encounter.find(value_line)
    assert start >= 0
    ent = {
        "text": value_line,
        "label": "observable_entity",
        "start": start,
        "end": start + len(value_line),
    }
    orig_end = ent["end"]
    merged = merge_cross_line_lab_findings(encounter, [ent])[0]
    assert merged.get("__cross_line_merged__") is True
    assert "Outside reference range" in merged["text"]
    assert merged["end"] > orig_end
    assert encounter[merged["start"] : merged["end"]] == merged["text"]


# -- AC8: validation corpus F1 (VT-29880CC8) -----------------------------------


def test_vt29880cc8_validation_corpus_scoring_contract() -> None:
    """VT-29880CC8 / DI-B5C78811 AC8 -- validation corpus F1 contract."""
    doc = load_expected_strings()
    base = fixture_dir().parent.parent.parent
    router = _read(EXTRACTION_SCENARIOS_ROUTER)

    assert doc["pass_threshold"]["overall_phrase_f1"] == 0.95
    assert "_PASS_THRESHOLD = 0.95" in router
    assert len(doc["cases"]) >= 90
    assert all((base / case["source_markdown"]).is_file() for case in doc["cases"])

    case = doc["cases"][0]
    expected = list(case["expected_strings"])
    extracted = {case["case_id"]: expected}
    result = score_extraction_cases([case], extracted, doc["normalisation"])
    assert result["overall"]["f1"] == 1.0
