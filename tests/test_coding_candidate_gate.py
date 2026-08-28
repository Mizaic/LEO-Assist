"""Cheap SNOMED shortlist filters before the coding verifier LLM.

Atlas trace:
  VT: VT-C265FD93
  DI: DI-0EC8620E
"""

from __future__ import annotations

from libs.pipeline.coding_candidate_gate import (
    filter_coding_candidates,
    tags_compatible,
)


def test_tags_reject_substance_for_clinical_finding() -> None:
    assert tags_compatible("finding", "substance") is False
    assert tags_compatible("finding", "finding") is True
    assert tags_compatible("finding", "disorder") is True
    assert tags_compatible("substance", "finding") is False
    assert tags_compatible("procedure", "substance") is False
    assert tags_compatible("finding", "observable_entity") is True


def test_filter_drops_cross_family_and_blocked_pairs() -> None:
    entity = {"text": "Allergy, unspecified", "label": "finding"}
    candidates = [
        {
            "concept_id": "16294009",
            "term": "Splenomegaly",
            "semantic_tag": "finding",
            "score": 0.94,
        },
        {
            "concept_id": "227420009",
            "term": "Gelatin",
            "semantic_tag": "substance",
            "score": 0.80,
        },
        {
            "concept_id": "419199007",
            "term": "Allergy to substance",
            "semantic_tag": "finding",
            "score": 0.78,
        },
    ]

    kept = filter_coding_candidates(
        entity,
        candidates,
        is_blocked=lambda text, cid: text.lower().startswith("allergy")
        and cid == "16294009",
    )

    assert [c["concept_id"] for c in kept] == ["419199007"]
