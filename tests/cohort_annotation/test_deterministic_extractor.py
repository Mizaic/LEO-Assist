"""Tests for the deterministic lab/vitals extractor."""

import pytest

from libs.cohort_annotation.deterministic_extractor import (
    extract_structured_entities,
    sentence_has_structured_content,
)


def _make_sents(texts):
    return [{"sentence_id": i + 1, "text": t} for i, t in enumerate(texts)]


# ---------------------------------------------------------------------------
# Lab triple detection
# ---------------------------------------------------------------------------

def test_lab_line_with_interpretation():
    sents = _make_sents([
        "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range"
    ])
    ents = extract_structured_entities(sents)
    labels = sorted(set(l for e in ents for l in e["labels"]))
    assert "PROCEDURE" in labels
    assert "OBSERVABLE_ENTITY" in labels
    assert "FINDING" in labels


def test_lab_line_no_interpretation():
    sents = _make_sents([
        "Haemoglobin estimation (423..) 138 g/L [120 - 160]"
    ])
    ents = extract_structured_entities(sents)
    label_set = {l for e in ents for l in e["labels"]}
    assert "PROCEDURE" in label_set
    assert "OBSERVABLE_ENTITY" in label_set
    assert "FINDING" not in label_set


def test_lab_requested_only():
    sents = _make_sents(["Full Blood Count (Requested)"])
    ents = extract_structured_entities(sents)
    # no value -> no extraction from lab_span_detector; may be empty
    # (that's correct; narrative node would extract the PROCEDURE)
    assert isinstance(ents, list)


def test_procedure_quote_is_substring_of_sentence():
    text = "Haemoglobin estimation (423..) 138 g/L [120 - 160]"
    sents = _make_sents([text])
    ents = extract_structured_entities(sents)
    proc = next(e for e in ents if "PROCEDURE" in e["labels"])
    assert proc["quote"] in text


def test_observable_entity_quote_is_substring_of_sentence():
    text = "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]"
    sents = _make_sents([text])
    ents = extract_structured_entities(sents)
    obs = next(e for e in ents if "OBSERVABLE_ENTITY" in e["labels"])
    assert obs["quote"] in text


def test_all_entities_tagged_deterministic():
    sents = _make_sents([
        "Serum sodium (XE2q9) 140 mmol/L"
    ])
    ents = extract_structured_entities(sents)
    for e in ents:
        assert e.get("source") == "deterministic"


def test_sentence_has_structured_content_true():
    assert sentence_has_structured_content("Serum sodium (XE2q9) 140 mmol/L")


def test_sentence_has_structured_content_false():
    assert not sentence_has_structured_content("Patient presents with a breast lump noticed 3 weeks ago.")


# ---------------------------------------------------------------------------
# Shared-start invariant on output quotes
# ---------------------------------------------------------------------------

def test_nested_spans_share_start():
    text = (
        "Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] - Outside reference range"
    )
    sents = _make_sents([text])
    ents = extract_structured_entities(sents)
    # All quotes should start at the same position in the sentence
    starts = {text.find(e["quote"]) for e in ents if e["quote"] in text}
    assert len(starts) == 1, f"starts differ: {starts}, ents: {[(e['labels'], e['quote']) for e in ents]}"


# ---------------------------------------------------------------------------
# Multiple sentences
# ---------------------------------------------------------------------------

def test_multiple_sentences():
    sents = _make_sents([
        "Haemoglobin estimation (423..) 138 g/L [120 - 160]",
        "Patient reports intermittent headaches.",
        "Serum sodium (XE2q9) 140 mmol/L",
    ])
    ents = extract_structured_entities(sents)
    sids_with_ents = {e["sentence_id"] for e in ents}
    assert 1 in sids_with_ents
    assert 3 in sids_with_ents
    assert 2 not in sids_with_ents  # prose sentence produces no deterministic entities
