"""Tests for deterministic relation closure (R16d + finding_site)."""

import pytest

from libs.cohort_annotation.relation_closure import (
    add_deterministic_relations,
    needs_llm_relation_pass,
)


def _e(id_, sid, quote, labels):
    return {"id": id_, "sentence_id": sid, "quote": quote, "labels": labels,
            "assertion": "present", "source": "deterministic"}


LAB_PROC  = _e("e1", 1, "Reticulocyte count - observation (42X..)", ["PROCEDURE"])
LAB_OBS   = _e("e2", 1, "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]", ["OBSERVABLE_ENTITY"])
LAB_FIND  = _e("e3", 1, "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range", ["FINDING"])


# ---------------------------------------------------------------------------
# R16d relations
# ---------------------------------------------------------------------------

def test_component_of_emitted_for_lab_pair():
    rels = add_deterministic_relations([LAB_PROC, LAB_OBS])
    types = [r["type"] for r in rels]
    assert "component_of" in types


def test_interprets_emitted_for_full_triple():
    rels = add_deterministic_relations([LAB_PROC, LAB_OBS, LAB_FIND])
    types = [r["type"] for r in rels]
    assert "interprets" in types
    assert "component_of" in types


def test_component_of_direction():
    rels = add_deterministic_relations([LAB_PROC, LAB_OBS])
    comp_rels = [r for r in rels if r["type"] == "component_of"]
    assert len(comp_rels) == 1
    assert comp_rels[0]["head_id"] == "e2"  # OBSERVABLE_ENTITY
    assert comp_rels[0]["tail_id"] == "e1"  # PROCEDURE


def test_interprets_direction():
    rels = add_deterministic_relations([LAB_PROC, LAB_OBS, LAB_FIND])
    interp_rels = [r for r in rels if r["type"] == "interprets"]
    assert len(interp_rels) == 1
    assert interp_rels[0]["head_id"] == "e3"  # FINDING
    assert interp_rels[0]["tail_id"] == "e2"  # OBSERVABLE_ENTITY


def test_no_relations_for_unrelated_entities():
    e_dis = _e("e1", 1, "carcinoma of prostate", ["DISORDER"])
    e_med = _e("e2", 1, "Decapeptyl SR", ["CLINICAL_DRUG"])
    rels = add_deterministic_relations([e_dis, e_med])
    assert rels == []


def test_deduplication_of_existing_relations():
    existing = [{"head_id": "e2", "tail_id": "e1", "type": "component_of",
                 "confidence": 0.99, "rationale": "already there"}]
    rels = add_deterministic_relations([LAB_PROC, LAB_OBS], existing_relations=existing)
    comp_rels = [r for r in rels if r["type"] == "component_of"]
    assert len(comp_rels) == 1  # no dupe


# ---------------------------------------------------------------------------
# Simple finding_site
# ---------------------------------------------------------------------------

def test_finding_site_for_finding_containing_body_structure():
    finding = _e("e1", 1, "lump in left breast", ["FINDING"])
    body    = _e("e2", 1, "left breast", ["BODY_STRUCTURE"])
    rels = add_deterministic_relations([finding, body])
    types = [r["type"] for r in rels]
    assert "finding_site" in types


def test_no_finding_site_when_no_body_structure():
    finding = _e("e1", 1, "weight loss", ["FINDING"])
    rels = add_deterministic_relations([finding])
    assert not any(r["type"] == "finding_site" for r in rels)


# ---------------------------------------------------------------------------
# needs_llm_relation_pass
# ---------------------------------------------------------------------------

def test_needs_llm_pass_with_finding_and_body():
    ents = [
        _e("e1", 1, "irregular lump", ["FINDING"]),
        _e("e2", 1, "left breast", ["BODY_STRUCTURE"]),
    ]
    assert needs_llm_relation_pass(ents) is True


def test_no_llm_pass_for_labs_only():
    ents = [LAB_PROC, LAB_OBS, LAB_FIND]
    assert needs_llm_relation_pass(ents) is False
