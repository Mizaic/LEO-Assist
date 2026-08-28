"""Known first-hit accidents must not survive merge + cheap reject.

Atlas trace:
  VT: VT-C265FD93
  DI: DI-0EC8620E

These four mappings were accepted on the five-patient Sherwood run when
the worker took candidates[0] and the verifier only saw that one code.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.coding_candidate_gate import filter_coding_candidates
from libs.pipeline_graph.subgraphs.coding_verifier import _verify_entities
from libs.pipeline_graph.subgraphs.terminology import _merge_resolution
from libs.terminology.client import ResolvedTerm


def _rt(concept_id: str, term: str, tag: str, score: float) -> ResolvedTerm:
    return ResolvedTerm(
        text="lookup",
        concept_id=concept_id,
        term=term,
        semantic_tag=tag,
        score=score,
    )


def test_allergy_does_not_keep_splenomegaly_first_hit() -> None:
    entity = {"text": "Allergy, unspecified", "label": "finding"}
    merged = _merge_resolution(
        entity,
        [
            _rt("16294009", "Splenomegaly", "finding", 0.94),
            _rt("419199007", "Allergy to substance", "finding", 0.81),
        ],
        min_score=0.55,
    )
    assert merged["concept_id"] != "16294009"
    assert "16294009" not in {
        c["concept_id"] for c in merged.get("coding_candidates") or []
    }


def test_vaseline_does_not_keep_gelatin_first_hit() -> None:
    entity = {"text": "Vaseline", "label": "substance"}
    merged = _merge_resolution(
        entity,
        [
            _rt("227420009", "Gelatin", "substance", 0.88),
            _rt("84812008", "Petroleum jelly", "substance", 0.79),
        ],
        min_score=0.55,
    )
    assert merged["concept_id"] != "227420009"
    ids = {c["concept_id"] for c in merged.get("coding_candidates") or []}
    assert "227420009" not in ids


def test_no_free_fluid_drops_csf_substance_by_tag() -> None:
    entity = {"text": "No free fluid", "label": "finding"}
    merged = _merge_resolution(
        entity,
        [
            _rt("116176007", "Cerebrospinal fluid", "substance", 0.90),
            _rt("168123008", "Free fluid in peritoneal cavity", "finding", 0.77),
        ],
        min_score=0.55,
    )
    assert merged["concept_id"] == "168123008"
    assert merged["term"] == "Free fluid in peritoneal cavity"


def test_high_bmi_does_not_keep_decreased_bmi() -> None:
    entity = {"text": "high BMI", "label": "finding"}
    merged = _merge_resolution(
        entity,
        [
            _rt("6497000", "Decreased body mass index", "finding", 0.91),
            _rt("162864005", "Body mass index 30+ - obesity", "finding", 0.80),
        ],
        min_score=0.55,
    )
    assert merged["concept_id"] != "6497000"
    assert "6497000" not in {
        c["concept_id"] for c in merged.get("coding_candidates") or []
    }


def test_verifier_reject_all_on_remaining_wrong_shortlist() -> None:
    entity = {
        "text": "Vaseline",
        "label": "substance",
        "semantic_tag": "substance",
        "concept_id": "84812008",
        "term": "Petroleum jelly",
        "coding_candidates": [
            {
                "concept_id": "84812008",
                "term": "Petroleum jelly",
                "semantic_tag": "substance",
                "score": 0.79,
            }
        ],
        "had_exact_match": False,
        "terminology_unresolved": False,
    }
    kept = filter_coding_candidates(
        entity,
        entity["coding_candidates"],
        is_blocked=lambda _text, _cid: False,
    )
    assert kept
    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=[
            {
                "index": 0,
                "verdict": "reject_all",
                "selected_index": None,
                "reason": "not a food",
            }
        ],
    ):
        result = _verify_entities(
            {
                "entities": [entity],
                "encounter_text": "Uses Vaseline (petroleum jelly).",
                "errors": [],
            }
        )
    assert result["entities"][0]["concept_id"] is None
    assert result["entities"][0]["terminology_unresolved"] is True
