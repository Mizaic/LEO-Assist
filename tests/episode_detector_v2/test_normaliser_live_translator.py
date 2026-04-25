"""Tests for the live-graph row translator inside normaliser.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

Covers the schema-binding layer added on 2026-04-22 after the dry-run
against patient 9990001004 surfaced that the original normaliser
queried a fictional schema. These tests exercise the translator
without touching Neo4j -- the integration test in
``tests/episode_detector_v2/test_normaliser_live_neo4j.py`` covers
the round-trip against the live dev graph and is gated on
``LIVE_NEO4J=1``.
"""

from __future__ import annotations

import json

from services.analysis_worker.app.episode_detector_v2.normaliser import (
    _is_referral_doc,
    _parse_assertion,
    _row_from_live,
    normalise_from_rows,
)


def _doc(**overrides):
    base = {
        "concept_id": "395557000",
        "display_name": "Breast lump",
        "semantic_tag": "Clinical_finding",
        "assertion_json": None,
        "modifiers_json": "{}",
        "evidence_sentence": "patient reports lump",
        "value": None,
        "unit": None,
        "decision_tier": "high",
        "model_version": "v1",
    }
    base.update(overrides)
    return base


def _live_row(**overrides):
    base = {
        "encounter_id": "enc-1",
        "occurred_on": "2025-08-12",
        "encounter_text": "Patient seen with right breast lump.",
        "raw_codes": [_doc()],
    }
    base.update(overrides)
    return base


# -- _parse_assertion -----------------------------------------------------


def test_parse_assertion_present_default_when_blank():
    assert _parse_assertion(None) == "present"
    assert _parse_assertion("") == "present"


def test_parse_assertion_extracts_negated_from_context_json():
    ctx = json.dumps({"assertion": "present", "negated": True})
    assert _parse_assertion(ctx) == "negated"


def test_parse_assertion_handles_family_history():
    ctx = json.dumps({"assertion": "present", "family": True})
    assert _parse_assertion(ctx) == "family_history"


def test_parse_assertion_handles_planned_referral():
    ctx = json.dumps({"assertion": "planned", "planned": True})
    assert _parse_assertion(ctx) == "planned"


def test_parse_assertion_handles_uncertain():
    ctx = json.dumps({"assertion": "present", "uncertain": True})
    assert _parse_assertion(ctx) == "uncertain"


# -- _is_referral_doc -----------------------------------------------------


def test_is_referral_doc_breast_2ww_concept_recognised():
    doc = _doc(concept_id="276341000000100")
    assert _is_referral_doc(doc) == "breast"


def test_is_referral_doc_upper_gi_2ww_concept_recognised():
    doc = _doc(concept_id="276551000000108")
    assert _is_referral_doc(doc) == "upper_gi"


def test_is_referral_doc_urology_2ww_concept_recognised():
    doc = _doc(concept_id="276431000000102")
    assert _is_referral_doc(doc) == "prostate_urological"


def test_is_referral_doc_falls_back_to_name_for_unmapped_concept():
    doc = _doc(
        concept_id="9999999999999",
        display_name="Fast track referral for suspected lung cancer (procedure)",
    )
    assert _is_referral_doc(doc) == "lung"


def test_is_referral_doc_returns_none_for_non_referral():
    doc = _doc(
        concept_id="395557000",
        display_name="Tumour of breast (disorder)",
    )
    assert _is_referral_doc(doc) is None


# -- _row_from_live -------------------------------------------------------


def test_row_from_live_promotes_referral_doc_to_referral_form():
    row = _live_row(
        raw_codes=[
            _doc(
                concept_id="276341000000100",
                display_name="Fast track referral for suspected breast cancer (procedure)",
                semantic_tag="Procedure",
            )
        ]
    )
    out = _row_from_live(row)
    assert out["referral"] is not None
    assert out["referral"]["form_type"] == "2ww_breast"
    assert out["referral"]["urgency"] == "2ww"
    assert out["referral"]["source"] == "snomed_referral"


def test_row_from_live_uses_clinic_seen_finding_when_no_referral():
    row = _live_row(
        raw_codes=[
            _doc(
                concept_id="382431000000103",
                display_name="Seen in fast track suspected breast cancer clinic (finding)",
                semantic_tag="Clinical_finding",
            )
        ]
    )
    out = _row_from_live(row)
    assert out["referral"] is not None
    assert out["referral"]["form_type"] == "2ww_breast"
    assert out["referral"]["source"] == "clinic_seen_finding"


def test_row_from_live_translates_observable_with_value_to_observation():
    row = _live_row(
        raw_codes=[
            _doc(
                concept_id="1030791000000100",
                display_name="Prostate specific antigen level (observable entity)",
                semantic_tag="Observable_entity",
                value=12.5,
                unit="ng/mL",
            )
        ]
    )
    out = _row_from_live(row)
    assert len(out["observations"]) == 1
    assert out["observations"][0]["value"] == 12.5
    assert out["observations"][0]["unit"] == "ng/mL"


def test_row_from_live_marks_outside_reference_as_abnormal():
    row = _live_row(
        raw_codes=[
            _doc(
                concept_id="166160000",
                display_name="Prostate specific antigen outside reference range (finding)",
                semantic_tag="Observable_entity",
                value=12.5,
            )
        ]
    )
    out = _row_from_live(row)
    assert out["observations"][0]["interpretation"] == "abnormal"


def test_row_from_live_extracts_assertion_into_coded_entities():
    ctx = json.dumps({"assertion": "present", "negated": True})
    row = _live_row(
        raw_codes=[_doc(concept_id="395557000", assertion_json=ctx)]
    )
    out = _row_from_live(row)
    assert out["codes"][0]["assertion"] == "negated"


def test_row_from_live_then_normaliser_yields_timeline_event():
    row = _live_row(
        raw_codes=[
            _doc(
                concept_id="276341000000100",
                display_name="Fast track referral for suspected breast cancer (procedure)",
                semantic_tag="Procedure",
            ),
            _doc(
                concept_id="395557000",
                display_name="Tumour of breast (disorder)",
                semantic_tag="Disease",
            ),
        ]
    )
    translated = _row_from_live(row)
    events = normalise_from_rows([translated])
    assert len(events) == 1
    evt = events[0]
    assert evt.encounter_id == "enc-1"
    assert evt.referral_form is not None
    assert evt.referral_form["form_type"] == "2ww_breast"
    assert any(c["concept_id"] == "395557000" for c in evt.coded_entities)
