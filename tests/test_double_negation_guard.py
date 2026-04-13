"""Tests for the double-negation guard on pre-negated SNOMED situation concepts.

VT-LEO-AI-101 / DI-LEO-AI-101 / R-LEO-AI-069

The guard closes a patient-safety gap where ConText sets assertion=absent on
a SNOMED situation concept whose preferred term already encodes a negative
(e.g. "No suicidal thoughts (situation)" 134420004).  absent + already-absent
concept = clinical inversion.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline.post_processing import fix_double_negated_situations


def _ent(
    assertion: str,
    semantic_tag: str,
    term: str = "",
    concept_id: str = "",
) -> dict[str, Any]:
    return {
        "assertion": assertion,
        "semantic_tag": semantic_tag,
        "term": term,
        "concept_id": concept_id,
    }


# ---------------------------------------------------------------------------
# VT-101-TC-001 -- "No suicidal thoughts" corrected
# ---------------------------------------------------------------------------
def test_no_suicidal_thoughts_corrected():
    ent = _ent("absent", "situation", "No suicidal thoughts (situation)", "134420004")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "double_negated_situation"


# ---------------------------------------------------------------------------
# VT-101-TC-002 -- "No thoughts of deliberate self harm" corrected
# ---------------------------------------------------------------------------
def test_no_self_harm_thoughts_corrected():
    ent = _ent(
        "absent",
        "situation",
        "No thoughts of deliberate self harm (situation)",
        "401228008",
    )
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "double_negated_situation"


# ---------------------------------------------------------------------------
# VT-101-TC-003 -- finding entity NOT changed
# ---------------------------------------------------------------------------
def test_finding_entity_not_changed():
    ent = _ent("absent", "finding", "No suicidal thoughts")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "absent"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# VT-101-TC-004 -- present assertion NOT changed
# ---------------------------------------------------------------------------
def test_present_assertion_not_changed():
    ent = _ent("present", "situation", "No suicidal thoughts (situation)", "134420004")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# VT-101-TC-005 -- positive PT with absent assertion not changed
# ---------------------------------------------------------------------------
def test_positive_pt_absent_not_changed():
    ent = _ent("absent", "situation", "Suicidal thoughts (finding)")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "absent"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# VT-101-TC-006 -- idempotency
# ---------------------------------------------------------------------------
def test_idempotent():
    ent = _ent("absent", "situation", "No suicidal thoughts (situation)", "134420004")
    fix_double_negated_situations([ent])
    state_after_first = dict(ent)
    fix_double_negated_situations([ent])
    assert ent == state_after_first


# ---------------------------------------------------------------------------
# VT-101-TC-007 -- "Absence of" prefix corrected
# ---------------------------------------------------------------------------
def test_absence_of_prefix_corrected():
    ent = _ent("absent", "situation", "Absence of signs and symptoms (situation)")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "double_negated_situation"


# ---------------------------------------------------------------------------
# VT-101-TC-008 -- guard fires inside _resolve_terms (runtime path)
# ---------------------------------------------------------------------------
def test_resolve_terms_applies_guard():
    """Verify _resolve_terms calls fix_double_negated_situations."""
    from libs.pipeline_graph.subgraphs.terminology import _resolve_terms

    candidate = MagicMock()
    candidate.term = "No suicidal thoughts (situation)"
    candidate.semantic_tag = "situation"
    candidate.score = 0.95
    candidate.concept_id = "134420004"
    candidate.read_code = None
    candidate.raw = {}

    entity = {
        "text": "No suicidal thoughts",
        "semantic_tag": "situation",
        "assertion": "absent",
        "start": 0,
        "end": 20,
    }

    with patch(
        "libs.pipeline_graph.subgraphs.terminology.TerminologyClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.resolve.return_value = {"No suicidal thoughts": [candidate]}
        result = _resolve_terms({"entities": [entity], "confidence_threshold": 0.70})

    resolved = result["entities"][0]
    assert resolved["assertion"] == "present"
    assert resolved.get("_assertion_guard") == "double_negated_situation"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "prefix",
    ["Not applicable", "Never smoked", "Unable to walk"],
)
def test_other_negative_prefixes_corrected(prefix: str):
    ent = _ent("absent", "situation", f"{prefix} (situation)")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"


def test_empty_term_not_corrected():
    ent = _ent("absent", "situation", "")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "absent"


def test_disorder_entity_not_changed():
    ent = _ent("absent", "disorder", "No known drug allergies")
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "absent"


def test_label_field_used_when_semantic_tag_missing():
    """Guard falls back to 'label' key when 'semantic_tag' is absent."""
    ent = {
        "assertion": "absent",
        "label": "situation",
        "term": "No suicidal thoughts (situation)",
    }
    fix_double_negated_situations([ent])
    assert ent["assertion"] == "present"


def test_multiple_entities_only_matching_corrected():
    entities = [
        _ent("absent", "situation", "No suicidal thoughts (situation)", "134420004"),
        _ent("absent", "finding", "Chest pain"),
        _ent("present", "situation", "Diabetes mellitus type 2"),
        _ent("absent", "situation", "History of asthma (situation)"),
    ]
    fix_double_negated_situations(entities)
    assert entities[0]["assertion"] == "present"
    assert entities[1]["assertion"] == "absent"
    assert entities[2]["assertion"] == "present"
    assert entities[3]["assertion"] == "absent"
