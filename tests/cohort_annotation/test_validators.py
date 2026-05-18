"""Tests for annotation validators."""

import pytest

from libs.cohort_annotation.validators import (
    run_all_validators,
    validate_entities,
    validate_relations,
)


SENTS = [
    {"sentence_id": 1, "text": "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range"},
    {"sentence_id": 2, "text": "lump on left side"},
    {"sentence_id": 3, "text": "No skin changes."},
]


def _e(id_, sid, quote, labels=None, assertion="present"):
    return {
        "id": id_, "sentence_id": sid, "quote": quote,
        "labels": labels or ["FINDING"], "assertion": assertion,
        "source": "test",
    }


# ---------------------------------------------------------------------------
# validate_entities
# ---------------------------------------------------------------------------

def test_valid_entity_passes():
    e = _e("e1", 2, "lump on left side")
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 1
    assert len(drops) == 0


def test_empty_quote_is_dropped():
    e = _e("e1", 2, "")
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 0
    assert drops[0]["reason"] == "empty_quote"


def test_invalid_label_is_dropped():
    e = _e("e1", 2, "lump on left side", labels=["FOOBAR"])
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 0
    assert "invalid_label" in drops[0]["reason"]


def test_invalid_assertion_is_dropped():
    e = _e("e1", 2, "lump on left side", assertion="maybe")
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 0
    assert "invalid_assertion" in drops[0]["reason"]


def test_quote_not_in_sentence_is_dropped():
    e = _e("e1", 2, "completely made up text that is not in the sentence")
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 0
    assert drops[0]["reason"] == "quote_not_found_in_sentence"


def test_unknown_sentence_id_passes_through():
    e = _e("e1", 999, "some text")
    clean, drops = validate_entities([e], SENTS)
    assert len(clean) == 1


# ---------------------------------------------------------------------------
# validate_relations
# ---------------------------------------------------------------------------

def test_valid_component_of_passes():
    entities = [
        _e("e1", 1, "Reticulocyte count - observation (42X..)", ["PROCEDURE"]),
        _e("e2", 1, "Reticulocyte count - observation (42X..) 96 10^9/L", ["OBSERVABLE_ENTITY"]),
    ]
    rels = [{"head_id": "e2", "tail_id": "e1", "type": "component_of", "confidence": 0.99, "rationale": "R16d"}]
    clean, drops = validate_relations(rels, entities)
    assert len(clean) == 1


def test_invalid_relation_type_dropped():
    entities = [
        _e("e1", 2, "lump on left side", ["FINDING"]),
        _e("e2", 2, "left side", ["BODY_STRUCTURE"]),
    ]
    rels = [{"head_id": "e1", "tail_id": "e2", "type": "nonsense_rel", "confidence": 0.9, "rationale": "?"}]
    clean, drops = validate_relations(rels, entities)
    assert len(clean) == 0
    assert drops[0]["reason"].startswith("invalid_type")


def test_policy_violation_dropped():
    entities = [
        _e("e1", 2, "lump", ["BODY_STRUCTURE"]),
        _e("e2", 2, "left side", ["FINDING"]),
    ]
    rels = [{"head_id": "e1", "tail_id": "e2", "type": "interprets", "confidence": 0.9, "rationale": "?"}]
    clean, drops = validate_relations(rels, entities)
    assert len(clean) == 0
    assert "policy_violation" in drops[0]["reason"]


def test_missing_head_entity_dropped():
    entities = [_e("e2", 2, "left side", ["BODY_STRUCTURE"])]
    rels = [{"head_id": "e99", "tail_id": "e2", "type": "finding_site", "confidence": 0.9, "rationale": "?"}]
    clean, drops = validate_relations(rels, entities)
    assert len(clean) == 0


# ---------------------------------------------------------------------------
# run_all_validators integration
# ---------------------------------------------------------------------------

def test_run_all_validators_clean():
    entities = [
        _e("e1", 1, "Reticulocyte count - observation (42X..)", ["PROCEDURE"]),
        _e("e2", 1, "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]", ["OBSERVABLE_ENTITY"]),
    ]
    relations = [{"head_id": "e2", "tail_id": "e1", "type": "component_of", "confidence": 0.99, "rationale": "R16d"}]
    clean_e, clean_r, drops = run_all_validators(entities, relations, SENTS)
    assert len(clean_e) == 2
    assert len(clean_r) == 1
    assert len(drops) == 0
