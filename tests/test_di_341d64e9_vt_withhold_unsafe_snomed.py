"""VT for DI-341D64E9 AC2: withhold SNOMED attach and persist when match is not safe."""

from __future__ import annotations

from pathlib import Path

from libs.pipeline_graph.subgraphs.persist import _entity_persist_term
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

    # Asserted by calling the guard, not by matching its source text. The
    # old version searched persist.py for a literal line and broke when a
    # variable was renamed, which says nothing about whether an unsafe code
    # can still reach the record.
    tiers: dict[int, object] = {}
    unsafe = {"text": "fatigue", "terminology_unresolved": True, "concept_id": None}
    assert _entity_persist_term(unsafe, 0, [unsafe], tiers) is None

    scored_but_unresolved = {
        "text": "nerve compression",
        "concept_id": "372063002",
        "terminology_unresolved": True,
    }
    assert (
        _entity_persist_term(scored_but_unresolved, 0, [scored_but_unresolved], tiers)
        is None
    ), "a concept id must not be persisted while the match is flagged unsafe"

    safe = {
        "text": "type 2 diabetes",
        "concept_id": "44054006",
        "term": "Diabetes mellitus type 2",
        "semantic_tag": "disorder",
        "terminology_unresolved": False,
    }
    payload = _entity_persist_term(safe, 0, [safe], tiers)
    assert payload is not None
    assert payload["coding"]["snomed_concept_id"] == "44054006"

    persist_source = Path("libs/pipeline_graph/subgraphs/persist.py").read_text()
    assert "record_uncoded_phrases" in persist_source
