"""VT for DI-341D64E9 AC1: safe approved match attaches SNOMED concept ID and term."""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.terminology import _merge_resolution, _resolve_terms
from libs.terminology.client import ResolvedTerm, TerminologyClient


def test_for_each_extracted_clinical_fact_when_safe_match_attaches_snomed_concept_id_and_preferred_term() -> (
    None
):
    entity = {"text": "Type 2 diabetes mellitus", "label": "disorder"}
    candidates = [
        ResolvedTerm(
            text="Type 2 diabetes mellitus",
            concept_id="44054006",
            term="Diabetes mellitus type 2",
            semantic_tag="disorder",
            score=0.92,
        )
    ]

    merged = _merge_resolution(entity, candidates, min_score=0.55)

    assert merged["terminology_unresolved"] is False
    assert merged["concept_id"] == "44054006"
    assert merged["term"] == "Diabetes mellitus type 2"

    entities = [
        {"text": "Haemoglobin", "label": "procedure", "semantic_tag": "procedure"},
        {
            "text": "Haemoglobin 125 g/L",
            "label": "observable_entity",
            "semantic_tag": "observable_entity",
        },
    ]

    def _fake_batch(self, terms, expected_tags, runtime):
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
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.55}
        )

    resolved = result["resolved_entities"]
    attached = [r for r in resolved if not r.get("terminology_unresolved")]
    assert len(attached) == 2
    assert all(r.get("concept_id") and r.get("term") for r in attached)
