"""Tests for span closure (triple completion and deduplication)."""

import pytest

from libs.cohort_annotation.span_closure import close_lab_triples, deduplicate, merge_and_close


LAB_SENTENCE = "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range"
LAB_SENTS = [{"sentence_id": 1, "text": LAB_SENTENCE}]


def _proc(sid=1):
    return {
        "id": "d1", "sentence_id": sid,
        "quote": "Reticulocyte count - observation (42X..)",
        "labels": ["PROCEDURE"], "assertion": "present",
        "rationale": "det", "source": "deterministic",
    }


def _obs(sid=1):
    return {
        "id": "d2", "sentence_id": sid,
        "quote": "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]",
        "labels": ["OBSERVABLE_ENTITY"], "assertion": "present",
        "rationale": "det", "source": "deterministic",
    }


def _find(sid=1):
    return {
        "id": "d3", "sentence_id": sid,
        "quote": LAB_SENTENCE,
        "labels": ["FINDING"], "assertion": "present",
        "rationale": "det", "source": "deterministic",
    }


# ---------------------------------------------------------------------------
# close_lab_triples
# ---------------------------------------------------------------------------

def test_close_adds_observable_when_missing():
    entities = [_proc()]  # PROCEDURE only
    added = close_lab_triples(entities, LAB_SENTS)
    labels = {l for e in added for l in e["labels"]}
    assert "OBSERVABLE_ENTITY" in labels


def test_close_does_not_add_when_all_present():
    entities = [_proc(), _obs(), _find()]
    added = close_lab_triples(entities, LAB_SENTS)
    assert added == []


def test_close_adds_finding_when_interpretation_present():
    entities = [_proc(), _obs()]
    added = close_lab_triples(entities, LAB_SENTS)
    labels = {l for e in added for l in e["labels"]}
    assert "FINDING" in labels


def test_close_does_not_add_finding_when_no_interpretation():
    text = "Haemoglobin estimation (423..) 138 g/L [120 - 160]"
    sents = [{"sentence_id": 1, "text": text}]
    proc_e = {
        "id": "d1", "sentence_id": 1,
        "quote": "Haemoglobin estimation (423..)",
        "labels": ["PROCEDURE"], "assertion": "present",
        "rationale": "det", "source": "deterministic",
    }
    entities = [proc_e]
    added = close_lab_triples(entities, sents)
    for e in added:
        assert "FINDING" not in e["labels"]


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------

def test_deduplicate_removes_exact_dupes():
    ents = [_proc(), _proc(), _obs()]
    result = deduplicate(ents)
    assert len(result) == 2


def test_deduplicate_renumbers_ids():
    ents = [_proc(), _obs(), _find()]
    result = deduplicate(ents)
    ids = [e["id"] for e in result]
    assert ids == ["e1", "e2", "e3"]


# ---------------------------------------------------------------------------
# merge_and_close
# ---------------------------------------------------------------------------

def test_merge_and_close_end_to_end():
    result = merge_and_close(
        structured_entities=[_proc(), _obs()],
        structured_missing=[],
        narrative_entities=[],
        sentences=LAB_SENTS,
    )
    labels = {l for e in result for l in e["labels"]}
    # Should have all three lab labels
    assert "PROCEDURE" in labels
    assert "OBSERVABLE_ENTITY" in labels
    assert "FINDING" in labels
    # No duplicate ids
    ids = [e["id"] for e in result]
    assert len(ids) == len(set(ids))
