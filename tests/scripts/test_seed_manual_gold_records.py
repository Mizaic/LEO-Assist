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


# ----------------------------------------------------------------------
# TC-006  SNOMED-derived semantic_tag safety (R-LEO-AI-180)
# ----------------------------------------------------------------------


def test_tc_006_qualifier_value_concept_on_finding_label_is_rejected():
    """Repro of the manual_gold_seed_2026_04_17 regression: 'normal'
    labelled as 'finding' but the attached SNOMED concept is a
    qualifier_value. Must abort BEFORE write."""
    rec = {
        "tag": "BAD-qualifier-on-finding",
        "encounter_id": "00000000-0000-0000-0000-000000000000",
        "episode_prefix": "deadbeef",
        "text": "Result is normal today",
        "entities": [
            {
                "text": "normal",
                "label": "finding",
                # NOTE: declared semantic_tag intentionally OMITTED so
                # the qualifier-value-on-clinical-label rule fires (the
                # one R-LEO-AI-180 specifically calls out). When BOTH
                # are declared the earlier "declared disagrees with
                # term suffix" rule fires first; both are valid rejects
                # but this test pins the safety message users will see.
                "snomed_concept_id": "17621005",
                "snomed_term": "Normal (qualifier value)",
                "assertion": "present",
            }
        ],
    }
    with pytest.raises(ValueError, match="R-LEO-AI-180"):
        prepare_record(rec)


def test_tc_006_qualifier_value_concept_on_qualifier_value_label_is_accepted():
    rec = {
        "tag": "OK-qualifier-on-qualifier",
        "encounter_id": "00000000-0000-0000-0000-000000000000",
        "episode_prefix": "deadbeef",
        "text": "Result is normal today",
        "entities": [
            {
                "text": "normal",
                "label": "qualifier_value",
                "semantic_tag": "qualifier_value",
                "snomed_concept_id": "17621005",
                "snomed_term": "Normal (qualifier value)",
                "assertion": "present",
            }
        ],
    }
    prepared = prepare_record(rec)
    assert prepared.entities[0]["label"] == "qualifier_value"
    assert prepared.entities[0]["semantic_tag"] == "qualifier_value"


def test_tc_006_declared_tag_overridden_by_term_suffix():
    """Declared semantic_tag MUST agree with SNOMED term suffix when
    both are present and a covered synonym is not available."""
    rec = {
        "tag": "BAD-declared-disagrees",
        "encounter_id": "00000000-0000-0000-0000-000000000000",
        "episode_prefix": "deadbeef",
        "text": "Patient referred for biopsy",
        "entities": [
            {
                "text": "biopsy",
                "label": "procedure",
                # Declared procedure but term is (disorder) -- safety
                # check must reject (procedure has no disorder synonym).
                "semantic_tag": "procedure",
                "snomed_concept_id": "12345",
                "snomed_term": "Wrong concept (disorder)",
                "assertion": "present",
            }
        ],
    }
    with pytest.raises(ValueError, match="(disagrees|R-LEO-AI-180)"):
        prepare_record(rec)


def test_tc_006_finding_disorder_synonym_is_accepted():
    """The validator's existing finding<->disorder synonym must be
    honoured by the seed safety check too -- otherwise legitimate
    finding-labelled disorder concepts would be blocked."""
    rec = {
        "tag": "OK-finding-with-disorder-concept",
        "encounter_id": "00000000-0000-0000-0000-000000000000",
        "episode_prefix": "deadbeef",
        "text": "Diagnosis: prostate cancer",
        "entities": [
            {
                "text": "prostate cancer",
                "label": "finding",
                "semantic_tag": "finding",
                "snomed_concept_id": "399068003",
                "snomed_term": "Malignant tumor of prostate (disorder)",
                "assertion": "present",
            }
        ],
    }
    prepared = prepare_record(rec)
    # Authoritative tag from suffix overrides declared.
    assert prepared.entities[0]["semantic_tag"] == "disorder"
    assert prepared.entities[0]["label"] == "finding"


def test_tc_006_concept_id_without_term_is_rejected():
    rec = _benign_record()
    rec["entities"][0]["snomed_concept_id"] = "12345"
    rec["entities"][0]["snomed_term"] = ""
    with pytest.raises(ValueError, match="no snomed_term"):
        prepare_record(rec)


def test_tc_006_real_manifest_has_no_qualifier_on_clinical_after_fix():
    """End-to-end: the live manifest must seed cleanly under the
    new safety check after the 5 known offenders were relabelled."""
    manifest = load_manifest(MANIFEST_PATH)
    prepared = prepare_all(manifest)
    for rec in prepared:
        for ent in rec.entities:
            if "(qualifier value)" in ent["snomed_term"]:
                assert ent["label"] == "qualifier_value", (
                    f"{rec.tag}: qualifier_value SNOMED concept must be "
                    f"labelled qualifier_value, got {ent['label']!r}"
                )
                assert ent["semantic_tag"] == "qualifier_value"
