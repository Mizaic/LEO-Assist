"""VT for DI-341D64E9 AC2: withhold SNOMED attach and persist when match is not safe."""

from __future__ import annotations

from pathlib import Path

from libs.pipeline_graph.subgraphs.terminology import _merge_resolution
from libs.terminology.client import ResolvedTerm


def test_does_not_attach_or_persist_snomed_unless_top_candidate_is_safe() -> None:
    below_threshold = _merge_resolution(
        {"text": "fatigue", "label": "finding"},
        [
            ResolvedTerm(
                text="fatigue",
                concept_id="84229001",
                term="Fatigue",
                semantic_tag="finding",
                score=0.40,
            )
        ],
        min_score=0.55,
    )
    assert below_threshold["terminology_unresolved"] is True
    assert below_threshold["concept_id"] is None
    assert below_threshold["term"] is None

    blocklisted = _merge_resolution(
        {"text": "nerve compression", "label": "finding"},
        [
            ResolvedTerm(
                text="nerve compression",
                concept_id="372063002",
                term="Malignant neoplasm of nervous system",
                semantic_tag="finding",
                score=0.88,
            )
        ],
        min_score=0.55,
    )
    assert blocklisted["terminology_unresolved"] is True
    assert blocklisted["concept_id"] is None

    empty_shortlist = _merge_resolution(
        {"text": "unknown symptom", "label": "finding"},
        [],
        min_score=0.55,
    )
    assert empty_shortlist["terminology_unresolved"] is True
    assert empty_shortlist.get("concept_id") is None

    persist_source = Path("libs/pipeline_graph/subgraphs/persist.py").read_text()
    assert 'if not concept_id or e.get("terminology_unresolved"):' in persist_source
