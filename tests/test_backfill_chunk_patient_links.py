"""Plan patient and encounter links from existing letter-chunk codes.

Atlas trace:
  DI: DI-58596C1A
  VT: VT-40032A1B
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-58596C1A")
"""

from __future__ import annotations

from scripts.backfill_chunk_patient_links import apply_statements, plan_chunk_link


def test_blank_assertion_is_treated_as_present() -> None:
    plan = plan_chunk_link(
        {
            "patient_id": "4245590920",
            "concept_id": "69896004",
            "name": "Rheumatoid arthritis",
            "semantic_tag": "disorder",
            "assertion": None,
            "referral_id": "rr-1",
            "has_shortcut": False,
            "has_encounter_doc": False,
        }
    )
    assert plan is not None
    assert plan.assertion == "present"
    assert plan.stamp_assertion is True
    assert plan.write_shortcut is True
    assert plan.shortcut_rel == "HAS_DISORDER"
    assert plan.encounter_id == "rr-1:referral-assessment"
    assert plan.write_encounter is True


def test_absent_code_does_not_get_a_patient_shortcut() -> None:
    plan = plan_chunk_link(
        {
            "patient_id": "4245590920",
            "concept_id": "443607001",
            "name": "Palpable mass",
            "semantic_tag": "finding",
            "assertion": "absent",
            "referral_id": "rr-1",
            "has_shortcut": False,
            "has_encounter_doc": False,
        }
    )
    assert plan is not None
    assert plan.write_shortcut is False
    assert plan.write_encounter is True
    assert plan.stamp_assertion is False


def test_existing_links_are_not_planned_again() -> None:
    plan = plan_chunk_link(
        {
            "patient_id": "4245590920",
            "concept_id": "364075005",
            "name": "Heart rate",
            "semantic_tag": "observable entity",
            "assertion": "present",
            "referral_id": "rr-1",
            "encounter_id": "enc-1",
            "has_shortcut": True,
            "has_encounter_doc": True,
        }
    )
    assert plan is None


def test_apply_statements_stamp_shortcut_and_encounter() -> None:
    plan = plan_chunk_link(
        {
            "patient_id": "4245590920",
            "concept_id": "69896004",
            "name": "Rheumatoid arthritis",
            "semantic_tag": "disorder",
            "assertion": None,
            "referral_id": "rr-1",
            "rel_id": "rel-1",
            "has_shortcut": False,
            "has_encounter_doc": False,
        }
    )
    assert plan is not None
    statements = apply_statements(plan)
    assert len(statements) == 3
    stamp_query, stamp_params = statements[0]
    shortcut_query, shortcut_params = statements[1]
    encounter_query, encounter_params = statements[2]
    assert "r.assertion IS NULL" in stamp_query
    assert stamp_params["assertion"] == "present"
    assert "HAS_DISORDER" in shortcut_query
    assert shortcut_params["patient_id"] == "4245590920"
    assert "MERGE (enc)-[er:DOCUMENTS" in encounter_query
    assert encounter_params["encounter_id"] == "rr-1:referral-assessment"


def test_apply_statements_rejects_unknown_shortcut_rel() -> None:
    plan = plan_chunk_link(
        {
            "patient_id": "4245590920",
            "concept_id": "69896004",
            "name": "Rheumatoid arthritis",
            "semantic_tag": "disorder",
            "assertion": "present",
            "encounter_id": "enc-1",
            "has_shortcut": False,
            "has_encounter_doc": True,
        }
    )
    assert plan is not None
    bad = plan.__class__(**{**plan.__dict__, "shortcut_rel": "HAS_HACK"})
    try:
        apply_statements(bad)
    except ValueError as exc:
        assert "HAS_HACK" in str(exc)
        return
    raise AssertionError("unknown shortcut rel must fail closed")
