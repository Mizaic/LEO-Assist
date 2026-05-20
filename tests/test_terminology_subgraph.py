from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.terminology import _merge_resolution, _resolve_terms
from libs.terminology.client import ResolvedTerm, TerminologyClient


def test_merge_resolution_blocks_over_specific_spinal_operation() -> None:
    entity = {"text": "spinal surgery", "label": "procedure"}
    candidates = [
        ResolvedTerm(
            text="spinal surgery",
            concept_id="1287097003",
            term="Unilateral biportal endoscopic operation on spine",
            semantic_tag="procedure",
            score=0.92,
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.70)

    assert merged["terminology_unresolved"] is True
    assert merged["concept_id"] is None
    assert merged["term"] is None


def test_merge_resolution_blocks_not_sleeping_well_to_malaise() -> None:
    entity = {"text": "not sleeping well", "label": "finding"}
    candidates = [
        ResolvedTerm(
            text="not sleeping well",
            concept_id="367391008",
            term="Malaise",
            semantic_tag="finding",
            score=0.90,
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.70)

    assert merged["terminology_unresolved"] is True
    assert merged["concept_id"] is None
    assert merged["term"] is None


def test_multi_classification_triple_each_gets_own_tag_hint() -> None:
    """procedure + observable_entity entities on the same lab line must each
    be resolved with their own entity-type hint.

    With full-text lookup (no lab value stripping), "Haemoglobin" (procedure)
    and "Haemoglobin 125 g/L" (observable_entity) are different lookup keys.
    A single batch call is made containing both terms.  The norm_tags dict
    carries the correct tag for each key so the server applies the right
    semantic-tag filter per term.
    """
    entities = [
        {"text": "Haemoglobin", "label": "procedure", "semantic_tag": "procedure"},
        {
            "text": "Haemoglobin 125 g/L",
            "label": "observable_entity",
            "semantic_tag": "observable_entity",
        },
    ]

    batch_calls: list[tuple[list[str], dict | None]] = []

    def _fake_batch(self, terms, expected_tags, runtime):
        batch_calls.append((list(terms), dict(expected_tags) if expected_tags else None))
        results = {}
        for term in terms:
            tag = (expected_tags or {}).get(term, "procedure")
            results[term] = [
                ResolvedTerm(
                    text=term,
                    concept_id=f"FAKE-{tag}",
                    term=f"{term} ({tag})",
                    semantic_tag=tag,
                    score=0.90,
                )
            ]
        return results

    with patch.object(TerminologyClient, "_resolve_batch", _fake_batch):
        result = _resolve_terms(
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.5}
        )

    resolved = result["resolved_entities"]
    assert len(resolved) == 2

    # With full-text lookup there is exactly one batch call containing both terms.
    assert len(batch_calls) == 1, (
        f"Expected a single batch call with both terms; got {len(batch_calls)} calls"
    )
    batch_terms, batch_tags = batch_calls[0]
    assert "Haemoglobin" in batch_terms
    assert "Haemoglobin 125 g/L" in batch_terms

    # Each term must carry its own entity-type tag hint in the batch.
    assert (batch_tags or {}).get("Haemoglobin") == "procedure", (
        f"Expected 'procedure' tag for 'Haemoglobin'; got: {batch_tags}"
    )
    assert (batch_tags or {}).get("Haemoglobin 125 g/L") == "observable_entity", (
        f"Expected 'observable_entity' tag for 'Haemoglobin 125 g/L'; got: {batch_tags}"
    )

    # Each entity must resolve to a distinct concept so the graph MERGE
    # produces two :DOCUMENTS links, not one.
    concept_ids = {
        r.get("concept_id") for r in resolved if not r.get("terminology_unresolved")
    }
    assert len(concept_ids) == 2, (
        f"Expected 2 distinct concept IDs (one per label), got {concept_ids}"
    )


def test_merge_resolution_blocks_nerve_compression_to_malignant_neoplasm() -> None:
    entity = {"text": "nerve compression", "label": "finding"}
    candidates = [
        ResolvedTerm(
            text="nerve compression",
            concept_id="372063002",
            term="Malignant neoplasm of nervous system",
            semantic_tag="finding",
            score=0.88,
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.70)

    assert merged["terminology_unresolved"] is True
    assert merged["concept_id"] is None
    assert merged["term"] is None


def test_merge_resolution_attaches_snomed_when_safe_match() -> None:
    entity = {"text": "Type 2 diabetes mellitus", "label": "disorder"}
    candidates = [
        ResolvedTerm(
            text="Type 2 diabetes mellitus",
            concept_id="44054006",
            term="Diabetes mellitus type 2",
            semantic_tag="disorder",
            score=0.92,
            read_code="C10..",
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.55)

    assert merged["terminology_unresolved"] is False
    assert merged["concept_id"] == "44054006"
    assert merged["term"] == "Diabetes mellitus type 2"
    assert merged["read_code"] == "C10.."


def test_merge_resolution_rejects_below_threshold() -> None:
    entity = {"text": "fatigue", "label": "finding"}
    candidates = [
        ResolvedTerm(
            text="fatigue",
            concept_id="84229001",
            term="Fatigue",
            semantic_tag="finding",
            score=0.40,
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.55)

    assert merged["terminology_unresolved"] is True
    assert merged["concept_id"] is None


def test_resolve_terms_logs_terminology_low_confidence_for_unresolved() -> None:
    entities = [{"text": "fatigue", "label": "finding"}]

    def _fake_batch(self, terms, expected_tags, runtime):
        return {
            "fatigue": [
                ResolvedTerm(
                    text="fatigue",
                    concept_id="84229001",
                    term="Fatigue",
                    semantic_tag="finding",
                    score=0.40,
                )
            ]
        }

    with patch.object(TerminologyClient, "_resolve_batch", _fake_batch):
        result = _resolve_terms(
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.55}
        )

    assert result["resolved_entities"][0]["terminology_unresolved"] is True
    assert any(
        err.startswith("terminology_low_confidence:")
        for err in result.get("errors") or []
    )
