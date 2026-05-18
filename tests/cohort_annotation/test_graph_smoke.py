"""Smoke test: run a full encounter through the graph with mocked LLM calls."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


SAMPLE_ENCOUNTER = {
    "patient_id": "TEST001",
    "encounter_id": "enc-abc",
    "encounter_date": "2025-03-10",
    "encounter_flags": "Face to face | Linked to Appointment",
    "text": (
        "History: F2F review. Breast lump.\n"
        "Noticed lump on left side last week.\n"
        "No FHx breast cancer.\n"
        "Plan: 2ww breast referral.\n"
        "Haemoglobin estimation (423..) 138 g/L [120 - 160]\n"
    ),
    "sentences": [
        {"sentence_id": 1, "text": "History: F2F review. Breast lump."},
        {"sentence_id": 2, "text": "Noticed lump on left side last week."},
        {"sentence_id": 3, "text": "No FHx breast cancer."},
        {"sentence_id": 4, "text": "Plan: 2ww breast referral."},
        {"sentence_id": 5, "text": "Haemoglobin estimation (423..) 138 g/L [120 - 160]"},
    ],
    "existing_coded_concepts": [],
    "patient_context": {"cancer_site": "breast", "diagnosis_date": "2025-04-14"},
}

ADMIN_ENCOUNTER = {
    "patient_id": "TEST001",
    "encounter_id": "enc-admin",
    "encounter_date": "2025-03-01",
    "encounter_flags": "Administration Event",
    "text": "Surgery: [STAFF] (Pharmacist)",
    "sentences": [{"sentence_id": 1, "text": "Surgery: [STAFF] (Pharmacist)"}],
    "existing_coded_concepts": [],
    "patient_context": {},
}


def _mock_llm_response(text: str) -> Any:
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.input_tokens = 100
    mock_resp.output_tokens = 50
    mock_resp.cached_input_tokens = 80
    return mock_resp


NARRATIVE_RESPONSE = json.dumps({"entities": [
    {"id": "n1", "sentence_id": 1, "quote": "F2F review",
     "labels": ["PROCEDURE"], "assertion": "present", "rationale": "exam act"},
    {"id": "n2", "sentence_id": 1, "quote": "Breast lump",
     "labels": ["FINDING"], "assertion": "present", "rationale": "symptom"},
    {"id": "n3", "sentence_id": 2, "quote": "lump on left side",
     "labels": ["FINDING"], "assertion": "present", "rationale": "exam finding"},
    {"id": "n4", "sentence_id": 3, "quote": "breast cancer",
     "labels": ["DISORDER"], "assertion": "family", "rationale": "FHx"},
    {"id": "n5", "sentence_id": 4, "quote": "2ww breast referral",
     "labels": ["PROCEDURE", "SITUATION"], "assertion": "planned", "rationale": "R7"},
]})

STRUCTURED_VERIFY_RESPONSE = json.dumps({"missed_entities": []})

RELATION_LINKER_RESPONSE = json.dumps({"relations": []})


def _mock_converse_side_effect(system, messages, **kwargs):
    agent_task = kwargs.get("agent_task", "")
    if "structured_verify" in agent_task:
        return _mock_llm_response(STRUCTURED_VERIFY_RESPONSE)
    if "narrative" in agent_task:
        return _mock_llm_response(NARRATIVE_RESPONSE)
    if "relation_linker" in agent_task:
        return _mock_llm_response(RELATION_LINKER_RESPONSE)
    return _mock_llm_response('{"entities": [], "missed_entities": [], "relations": []}')


@pytest.fixture()
def mock_llm():
    """Patch create_llm so that no actual Bedrock calls are made."""
    import libs.cohort_annotation.runner as runner_mod

    # Reset compiled graph cache so tests are isolated
    runner_mod._COMPILED_GRAPH = None

    mock_client = MagicMock()
    mock_client.converse.side_effect = _mock_converse_side_effect
    with patch(
        "libs.cohort_annotation.graph._get_llm",
        return_value=mock_client,
    ):
        yield mock_client

    runner_mod._COMPILED_GRAPH = None


def test_admin_encounter_produces_empty(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(ADMIN_ENCOUNTER)
    assert result.entities == []
    assert result.relations == []
    assert result.llm_calls == 0
    assert result.encounter_class == "EMPTY"
    assert result.annotation_complete is True


def test_mixed_encounter_produces_entities(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(SAMPLE_ENCOUNTER)
    assert result.annotation_complete is True
    assert len(result.entities) >= 5  # 5 narrative + 2 structured (Hb)
    # check encounter class not EMPTY
    assert result.encounter_class != "EMPTY"


def test_mixed_encounter_has_relations(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(SAMPLE_ENCOUNTER)
    # deterministic closure should have emitted component_of for Hb pair
    rel_types = {r["type"] for r in result.relations}
    assert "component_of" in rel_types


def test_mixed_encounter_no_qa_drops(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(SAMPLE_ENCOUNTER)
    # All LLM quotes in the mock are verbatim substrings, so there should be no drops
    assert result.qa_drops == [], f"Unexpected qa_drops: {result.qa_drops}"


def test_llm_calls_counted(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(SAMPLE_ENCOUNTER)
    assert result.llm_calls >= 2  # structured_verify + narrative


def test_to_dict_serialisable(mock_llm):
    from libs.cohort_annotation.runner import annotate_encounter
    result = annotate_encounter(SAMPLE_ENCOUNTER)
    d = result.to_dict()
    assert isinstance(json.dumps(d), str)
