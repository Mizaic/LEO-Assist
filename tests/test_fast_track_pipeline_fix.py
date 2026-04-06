"""Tests for pipeline fixes that ensure fast-track cancer pathway encounters are coded.

VT-LEO-AI-084 -- TC-008 (sentence_splitter allowlist)
VT-LEO-AI-084 -- TC-009 (encounter_classifier clinical_override)
VT-LEO-AI-084 -- TC-010 (IS_A expansion enriches ValueSet concept buckets)
VT-LEO-AI-084 -- TC-011 (fast-track referral phrases preserved by splitter)
VT-LEO-AI-084 -- TC-012 (fast-track referral notes classified as clinical)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# TC-008: sentence_splitter preserves 'Seen in fast track' lines
# ---------------------------------------------------------------------------


def test_tc008_fast_track_line_preserved_through_filter():
    """Lines containing 'seen in fast track' must not be stripped even if the
    surrounding text matches a header-like pattern."""
    from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences, is_header_sentence

    # A line that starts with a timestamp (matches _HEADER_RE) but also has the phrase.
    # In practice, these are often template entries like:
    #   "10:30 Seen in fast track suspected breast cancer clinic"
    chunk_with_fast_track = SentenceChunk(
        sentence_id="s1",
        text="Seen in fast track suspected breast cancer clinic",
        start=0,
        end=50,
    )
    chunk_pure_header = SentenceChunk(
        sentence_id="s2",
        text="Entered at: GP surgery",
        start=51,
        end=75,
    )

    result = filter_header_sentences([chunk_with_fast_track, chunk_pure_header])

    # Fast-track chunk must survive
    assert chunk_with_fast_track in result, (
        "filter_header_sentences should preserve chunks containing 'seen in fast track'"
    )
    # Pure header is removed
    assert chunk_pure_header not in result, (
        "filter_header_sentences should remove pure admin header chunks"
    )


def test_tc008_fast_track_case_insensitive():
    """Allowlist check is case-insensitive."""
    from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences

    chunk = SentenceChunk(
        sentence_id="s1",
        text="SEEN IN FAST TRACK SUSPECTED LUNG CANCER CLINIC",
        start=0,
        end=47,
    )
    result = filter_header_sentences([chunk])
    assert chunk in result


def test_tc008_non_fast_track_header_is_removed():
    """A normal admin header with no fast-track text is still stripped."""
    from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences

    chunk = SentenceChunk(
        sentence_id="s1",
        text="Seen by practice phlebotomist",
        start=0,
        end=29,
    )
    result = filter_header_sentences([chunk])
    assert chunk not in result


# ---------------------------------------------------------------------------
# TC-009: encounter_classifier promotes 'Seen in fast track' to clinical
# ---------------------------------------------------------------------------


def test_tc009_fast_track_text_classified_as_clinical():
    """An encounter note containing 'Seen in fast track' must be classified
    as 'clinical', not 'admin_only'."""
    from libs.classifiers.encounter_textcat import classify_text

    text = (
        "2WW appointment completed.\n"
        "Seen in fast track suspected breast cancer clinic.\n"
        "Patient reviewed and onward management planned."
    )
    result = classify_text(text)
    assert result == "clinical", (
        f"Expected 'clinical' for fast-track note, got '{result}'"
    )


def test_tc009_seen_in_fast_track_short_note():
    """Even a very short secretary note with just the phrase is clinical."""
    from libs.classifiers.encounter_textcat import classify_text

    text = "Seen in fast track suspected colorectal cancer clinic"
    result = classify_text(text)
    assert result == "clinical", (
        f"Expected 'clinical', got '{result}'"
    )


def test_tc009_2ww_clinic_classified_as_clinical():
    """'Seen in 2WW clinic' variant is also promoted by the override."""
    from libs.classifiers.encounter_textcat import classify_text

    text = "Seen in 2WW clinic for urology review"
    result = classify_text(text)
    assert result == "clinical", (
        f"Expected 'clinical' for '2WW clinic' note, got '{result}'"
    )


# ---------------------------------------------------------------------------
# TC-010: IS_A expansion enriches ValueSet concept buckets
# ---------------------------------------------------------------------------


def test_tc010_isa_expansion_adds_children_to_valueset():
    """_expand_valuesets_with_isa() should inject child concept IDs returned
    by the KG IS_A query into each ValueSet's compose.include[].concept list."""
    from libs.pipeline_graph.subgraphs.anchor import _expand_valuesets_with_isa

    parent_id = "363358000"
    child_ids = ["1234567890", "9876543210", "1111111111"]

    valuesets = {
        "cancer_types": {
            "compose": {
                "include": [
                    {
                        "concept": [{"code": parent_id, "display": "Malignant neoplasm"}]
                    }
                ]
            }
        }
    }

    mock_kg = MagicMock()
    mock_kg.run.return_value = [
        {"parent_id": parent_id, "child_id": cid, "display": f"Child {cid}"}
        for cid in child_ids
    ]

    result = _expand_valuesets_with_isa(mock_kg, valuesets)

    codes_in_result = [
        c["code"]
        for include in result["cancer_types"]["compose"]["include"]
        for c in include["concept"]
    ]
    for cid in child_ids:
        assert cid in codes_in_result, f"Child {cid} not in expanded ValueSet"
    assert parent_id in codes_in_result, "Parent concept must still be present"


def test_tc010_child_concept_matched_in_bucket():
    """After IS_A expansion, a child concept ID should be classified into
    the correct milestone bucket by _classify_anchor_rows."""
    from libs.pipeline_graph.subgraphs.anchor import _expand_valuesets_with_isa
    from services.analysis_worker.app.analyzers.anchor_detector import (
        _classify_anchor_rows,
    )
    from libs.domain_config.registry import DomainRegistry, NCDADomain

    parent_id = "363358000"
    child_id = "999000001"

    valuesets = {
        "cancer_types": {
            "compose": {
                "include": [
                    {"concept": [{"code": parent_id, "display": "Malignant neoplasm"}]}
                ]
            }
        }
    }

    mock_kg = MagicMock()
    mock_kg.run.return_value = [
        {"parent_id": parent_id, "child_id": child_id, "display": "Child neoplasm"}
    ]

    expanded = _expand_valuesets_with_isa(mock_kg, valuesets)

    # Build a minimal DomainRegistry from the expanded valuesets
    registry = DomainRegistry.from_fhir(expanded)

    # Patch _domain_configs so the registry recognises cancer_types as diagnosis milestone
    diag_mock = MagicMock(spec=NCDADomain)
    diag_mock.milestone_type = "diagnosis"
    diag_mock.assertion_filter = []
    registry._domain_configs["cancer_types"] = diag_mock  # type: ignore[attr-defined]

    # Patch _concepts so get_concept_ids() returns both parent and child as ints
    from libs.domain_config.registry import NCDAConcept

    def _make_concept(code: str) -> NCDAConcept:
        c = MagicMock(spec=NCDAConcept)
        c.concept_id = int(code)
        return c

    registry._concepts["cancer_types"] = [  # type: ignore[attr-defined]
        _make_concept(parent_id),
        _make_concept(child_id),
    ]

    from services.analysis_worker.app.analyzers.anchor_detector import _build_buckets, _classify_anchor_rows

    buckets = _build_buckets(registry)
    rows = [
        {
            "encounter_id": "enc-001",
            "encounter_date": "2026-01-10",
            "concept_id": int(child_id),
            "concept_name": "Child neoplasm",
            "assertion": "present",
        }
    ]
    referrals, diagnoses, treatments, specialists = _classify_anchor_rows(rows, buckets)

    assert len(diagnoses) == 1, (
        f"Child concept {child_id} should be classified as a diagnosis anchor"
    )
    assert diagnoses[0]["concept_id"] == int(child_id)


# ---------------------------------------------------------------------------
# TC-011: sentence_splitter preserves fast-track referral lines
# ---------------------------------------------------------------------------


def test_tc011_fast_track_referral_line_preserved():
    """Lines containing 'fast track referral for suspected' must survive the
    header filter even when the surrounding context is admin-only."""
    from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences

    referral_chunk = SentenceChunk(
        sentence_id="r1",
        text="Fast track referral for suspected breast cancer",
        start=0,
        end=47,
    )
    header_chunk = SentenceChunk(
        sentence_id="h1",
        text="Entered at: LLR SPA",
        start=48,
        end=68,
    )
    result = filter_header_sentences([referral_chunk, header_chunk])
    assert referral_chunk in result, (
        "filter_header_sentences should preserve 'fast track referral for suspected' chunks"
    )
    assert header_chunk not in result


def test_tc011_generic_fast_track_cancer_referral_preserved():
    """'Fast track cancer referral' (generic) is also preserved."""
    from libs.nlp.sentence_splitter import SentenceChunk, filter_header_sentences

    chunk = SentenceChunk("r2", "Fast track cancer referral", 0, 26)
    result = filter_header_sentences([chunk])
    assert chunk in result


# ---------------------------------------------------------------------------
# TC-012: encounter_classifier promotes fast-track referral notes to clinical
# ---------------------------------------------------------------------------


def test_tc012_fast_track_referral_classified_clinical():
    """A secretary note with 'fast track referral for suspected X' must be
    promoted to 'clinical' not left as 'admin_only'."""
    from libs.classifiers.encounter_textcat import classify_text

    notes = [
        "10:12 - Surgery: JONES, Emma (Medical Secretary Access Role) \nFast track referral for suspected lower GI cancer",
        "12:52 - Surgery: HUBBARD, Siobhan (Medical Secretary Access Role) \nFast track referral for suspected breast cancer",
        "12:12 - Surgery: JONES, Emma (Medical Secretary Access Role) \nFast track referral for suspected brain tumour",
        "Fast track referral for suspected head and neck cancer",
        "PRISM 2WW Upper GI - Fast track referral for suspected upper GI cancer",
    ]
    for text in notes:
        result = classify_text(text)
        assert result == "clinical", (
            f"Expected 'clinical' for referral note, got '{result}': {text[:60]!r}"
        )


# ---------------------------------------------------------------------------
# TC-013: Post-processing suppression guard for 395100000 screening FPs
# ---------------------------------------------------------------------------


def test_tc013_screening_negatives_suppressed_by_guard():
    """Routine screening negatives must be removed by the concept suppression
    guard before they reach the coding queue."""
    from libs.pipeline.post_processing import _suppress_screening_false_positives

    screening_false_positives = [
        {"snomed_concept_id": "395100000", "text": "Negative cervical cytology. Normal recall."},
        {"snomed_concept_id": "395100000", "text": "HPV Test: High risk HPV not detected"},
        {"snomed_concept_id": "395100000", "text": "NEGATIVE FIT - No Further Action"},
        {"snomed_concept_id": "395100000", "text": "overall negative result"},
        {"snomed_concept_id": "395100000", "text": "Sent following an overall negative result"},
        {"snomed_concept_id": "395100000", "text": "Cervical smear: negative"},
        {"snomed_concept_id": "395100000", "text": "Bowel cancer screening programme: faecal occult blood"},
        {"snomed_concept_id": "395100000", "text": "no detectable blood and the risk of CRC is less than 1 in 1000"},
    ]
    result = _suppress_screening_false_positives(screening_false_positives)
    assert result == [], (
        f"Expected all screening FPs suppressed, got {len(result)} remaining: {result}"
    )


def test_tc013_legitimate_no_cancer_codings_preserved():
    """Genuine post-pathway 'no evidence of cancer' codings must pass through
    the suppression guard unchanged."""
    from libs.pipeline.post_processing import _suppress_screening_false_positives

    legitimate = [
        {"snomed_concept_id": "395100000", "text": "No evidence of cancer found"},
        {"snomed_concept_id": "395100000", "text": "No evidence of malignancy"},
        {"snomed_concept_id": "395100000", "text": "no cancer on CT"},
        {"snomed_concept_id": "395100000", "text": "No evidence of cancer was seen on this endoscopy"},
        {"snomed_concept_id": "395100000", "text": "benign on histology"},
        {"snomed_concept_id": "363358000", "text": "Malignant neoplasm of breast"},
    ]
    result = _suppress_screening_false_positives(legitimate)
    assert len(result) == len(legitimate), (
        f"Expected all {len(legitimate)} legitimate entities kept, got {len(result)}"
    )
