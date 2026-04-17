"""VT-LEO-AI-160 unit tests for scripts/seed_manual_gold_records.py.

Covers:
- TC-001  manifest schema and span validity
- TC-002  PHI rejection (residual postcode/email/etc must abort)
- TC-003  idempotency (deterministic candidate_id + label_id)
- TC-004  assertion vocabulary enforcement
- TC-005  label vocabulary enforcement (lowercase SNOMED semantic tags)
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.seed_manual_gold_records import (  # noqa: E402
    VALID_ASSERTIONS,
    VALID_LABELS,
    _candidate_id,
    _label_id,
    load_manifest,
    prepare_all,
    prepare_record,
)

MANIFEST_PATH = (
    REPO
    / "design-controls"
    / "training-data"
    / "manual-gold-seed-2026-04-17.yaml"
)


def _benign_record() -> dict:
    return {
        "tag": "TEST-benign",
        "encounter_id": "00000000-0000-0000-0000-000000000000",
        "episode_prefix": "deadbeef",
        "text": "Tubular adenoma (Xa98X)",
        "entities": [
            {
                "text": "Tubular adenoma",
                "label": "disorder",
                "semantic_tag": "disorder",
                "snomed_concept_id": "444068008",
                "snomed_term": "Tubular adenoma (disorder)",
                "assertion": "present",
            }
        ],
    }


# ----------------------------------------------------------------------
# TC-001  manifest schema + span validity
# ----------------------------------------------------------------------


def test_tc_001_real_manifest_loads_and_validates():
    manifest = load_manifest(MANIFEST_PATH)
    assert manifest["schema_version"] == "1.0"
    assert manifest["source"] == "manual_gold_seed_2026_04_17"
    assert manifest["verified_by"] == "rob_smith"
    assert manifest["quality_score"] == pytest.approx(0.95)

    prepared = prepare_all(manifest)
    assert len(prepared) == 21

    pos = [p for p in prepared if p.tag.startswith("POS-")]
    neg = [p for p in prepared if p.tag.startswith("NEG-")]
    assert len(pos) == 4
    assert len(neg) == 17

    for rec in prepared:
        assert rec.text
        assert rec.entities, f"{rec.tag} has no entities"
        for ent in rec.entities:
            text_slice = rec.text[ent["start"] : ent["end"]]
            assert text_slice.lower() == ent["text"].lower(), (
                f"{rec.tag} span mismatch: "
                f"sentence[{ent['start']}:{ent['end']}]={text_slice!r} "
                f"vs surface={ent['text']!r}"
            )


# ----------------------------------------------------------------------
# TC-002  PHI rejection
# ----------------------------------------------------------------------


def test_tc_002_postcode_in_text_is_rejected():
    rec = _benign_record()
    rec["text"] = "Tubular adenoma at SW1A 1AA clinic"
    rec["entities"][0]["text"] = "Tubular adenoma"
    with pytest.raises(ValueError, match="mutates under deidentify_text"):
        prepare_record(rec)


def test_tc_002_email_in_text_is_rejected():
    rec = _benign_record()
    rec["text"] = "Tubular adenoma noted; contact admin@example.org"
    rec["entities"][0]["text"] = "Tubular adenoma"
    with pytest.raises(ValueError, match="mutates under deidentify_text"):
        prepare_record(rec)


def test_tc_002_real_manifest_has_no_residual_phi():
    manifest = load_manifest(MANIFEST_PATH)
    prepare_all(manifest)


# ----------------------------------------------------------------------
# TC-003  idempotency
# ----------------------------------------------------------------------


def test_tc_003_candidate_id_is_deterministic():
    text = "Tubular adenoma (Xa98X)"
    a = _candidate_id(text)
    b = _candidate_id(text)
    assert a == b
    assert len(a) == 64
    assert _candidate_id(text + " ") != a


def test_tc_003_label_id_is_deterministic_and_order_independent():
    text = "Mammogram - normal"
    e1 = [{"text": "Mammogram"}, {"text": "normal"}]
    e2 = [{"text": "normal"}, {"text": "Mammogram"}]
    assert _label_id(text, e1) == _label_id(text, e2)
    assert _label_id(text, e1).startswith("GL-")
    assert len(_label_id(text, e1)) == 19


def test_tc_003_repeated_prepare_yields_identical_ids():
    rec = _benign_record()
    a = prepare_record(rec)
    b = prepare_record(copy.deepcopy(rec))
    assert a.candidate_id == b.candidate_id
    assert a.label_id == b.label_id
    assert a.entities == b.entities


# ----------------------------------------------------------------------
# TC-004  assertion vocabulary enforcement
# ----------------------------------------------------------------------


def test_tc_004_unknown_assertion_is_rejected():
    rec = _benign_record()
    rec["entities"][0]["assertion"] = "kinda_present"
    with pytest.raises(ValueError, match="VALID_ASSERTIONS"):
        prepare_record(rec)


def test_tc_004_all_canonical_assertions_are_accepted():
    for assertion in VALID_ASSERTIONS:
        rec = _benign_record()
        rec["entities"][0]["assertion"] = assertion
        prepared = prepare_record(rec)
        assert prepared.entities[0]["assertion"] == assertion


# ----------------------------------------------------------------------
# TC-005  label vocabulary enforcement
# ----------------------------------------------------------------------


def test_tc_005_unknown_label_is_rejected():
    rec = _benign_record()
    rec["entities"][0]["label"] = "diagnosis"  # not a SNOMED semantic tag
    with pytest.raises(ValueError, match="VALID_LABELS"):
        prepare_record(rec)


def test_tc_005_uppercase_label_is_rejected_unless_in_vocabulary():
    rec = _benign_record()
    rec["entities"][0]["label"] = "DISORDER"
    rec["entities"][0]["semantic_tag"] = "DISORDER"
    prepared = prepare_record(rec)
    assert prepared.entities[0]["label"] == "disorder"


def test_tc_005_real_manifest_uses_only_valid_labels():
    manifest = load_manifest(MANIFEST_PATH)
    prepared = prepare_all(manifest)
    for rec in prepared:
        for ent in rec.entities:
            assert ent["label"] in VALID_LABELS, (
                f"{rec.tag}: unexpected label {ent['label']!r}"
            )
            assert ent["assertion"] in VALID_ASSERTIONS, (
                f"{rec.tag}: unexpected assertion {ent['assertion']!r}"
            )


# ----------------------------------------------------------------------
# Span resolution
# ----------------------------------------------------------------------


def test_missing_surface_text_is_rejected():
    rec = _benign_record()
    rec["entities"][0]["text"] = "this phrase is not in the sentence"
    with pytest.raises(ValueError, match="cannot locate surface text"):
        prepare_record(rec)
