from __future__ import annotations

from libs.pipeline_graph.subgraphs.terminology import _merge_resolution
from libs.terminology.client import ResolvedTerm


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
