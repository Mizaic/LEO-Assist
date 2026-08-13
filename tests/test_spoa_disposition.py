"""Tests for advisory SPoA disposition mapping."""

from __future__ import annotations

from libs.sbar.spoa_disposition import (
    derive_spoa_disposition,
    disposition_label,
    format_spoa_recommendation_markdown,
    prepend_spoa_disposition_to_recommendation,
)


def _rule(
    name: str, *, priority: str = "2ww", action_name: str = "Chest X-ray"
) -> dict:
    return {
        "rule_id": name,
        "name": name,
        "guideline_title": "Suspected cancer",
        "actions": [{"priority": priority, "name": action_name}],
    }


def test_primary_diagnostic_rule_maps_to_straight_to_test() -> None:
    code, evidence = derive_spoa_disposition(
        primary_rules=[_rule("breast-rule", action_name="Mammogram")],
        alternative_rules=[],
    )
    assert code == "straight_to_test"
    assert "matched" in (evidence or "").lower()


def test_referral_action_maps_to_outpatient_not_procedure() -> None:
    """A fast-track referral is an outpatient pathway, not a booked procedure.

    SNOMED CT tags nearly every action concept -- including referrals --
    under the procedure hierarchy, so the preferred term itself ends in
    the generic "(procedure)" semantic tag (e.g. "Fast track referral
    for suspected upper gastrointestinal cancer (procedure)"). Naively
    matching the bare word "procedure" wrongly routed every referral
    into the "procedure" disposition bucket.
    """
    code, evidence = derive_spoa_disposition(
        primary_rules=[
            _rule(
                "1.2.1",
                priority="2ww",
                action_name=(
                    "Fast track referral for suspected upper "
                    "gastrointestinal cancer (procedure)"
                ),
            )
        ],
        alternative_rules=[],
    )
    assert code == "outpatient_appointment"
    assert "1.2.1" in (evidence or "")


def test_direct_access_endoscopy_action_maps_to_procedure() -> None:
    """A genuine direct-access endoscopy still maps to the procedure bucket."""
    code, _ = derive_spoa_disposition(
        primary_rules=[
            _rule(
                "1.2.3",
                priority="routine",
                action_name="Esophagogastroduodenoscopy (procedure)",
            )
        ],
        alternative_rules=[],
    )
    assert code == "procedure"


def test_xray_action_with_procedure_semantic_tag_maps_to_straight_to_test() -> None:
    """An imaging action tagged "(procedure)" by SNOMED is still a test."""
    code, _ = derive_spoa_disposition(
        primary_rules=[
            _rule(
                "1.1.2",
                priority="urgent",
                action_name="Plain X-ray of chest (procedure)",
            )
        ],
        alternative_rules=[],
    )
    assert code == "straight_to_test"


def test_best_rule_and_evidence_stay_consistent_across_mixed_matches() -> None:
    """Reproduces the multi-rule NG12 UGI case: disposition label must
    match the actual action kind of the rule cited as evidence."""
    referral = _rule(
        "1.2.1",
        priority="2ww",
        action_name=(
            "Fast track referral for suspected upper "
            "gastrointestinal cancer (procedure)"
        ),
    )
    endoscopy = _rule(
        "1.2.3",
        priority="routine",
        action_name="Esophagogastroduodenoscopy (procedure)",
    )
    xray = _rule(
        "1.1.2",
        priority="urgent",
        action_name="Plain X-ray of chest (procedure)",
    )
    code, evidence = derive_spoa_disposition(
        primary_rules=[referral, endoscopy, xray],
        alternative_rules=[],
    )
    # 2ww outranks urgent/routine, so the referral rule is cited...
    assert "1.2.1" in (evidence or "")
    # ...and its disposition must describe a referral outcome, not a
    # booked procedure (the bug this test guards against).
    assert code == "outpatient_appointment"


def test_primary_miss_with_alternative_maps_to_referral() -> None:
    code, evidence = derive_spoa_disposition(
        primary_rules=[],
        alternative_rules=[_rule("alt-rule")],
    )
    assert code == "refer_to_alternative_service"
    assert evidence is not None


def test_communication_request_primary_match_maps_to_discussion() -> None:
    code, _ = derive_spoa_disposition(
        primary_rules=[_rule("ag-rule")],
        alternative_rules=[],
        source_node_type="CommunicationRequest",
    )
    assert code == "discussion_with_primary_care"


def test_disposition_label_is_plain_english() -> None:
    assert disposition_label("straight_to_test") == "Straight to test"


def test_format_spoa_recommendation_markdown() -> None:
    md = format_spoa_recommendation_markdown(
        "procedure",
        "Receiving service guidelines matched: Rule: 1.4.1.",
    )
    assert "**Advisory SPoA disposition:** Procedure." in md
    assert "Rule: 1.4.1" in md


def test_prepend_spoa_disposition_to_recommendation() -> None:
    combined = prepend_spoa_disposition_to_recommendation(
        "- Rule signals noted.",
        "procedure",
        "Receiving service guidelines matched: Rule: 1.4.1.",
    )
    assert combined.startswith("**Advisory SPoA disposition:** Procedure.")
    assert combined.endswith("- Rule signals noted.")


def test_prepend_spoa_disposition_without_llm_body() -> None:
    combined = prepend_spoa_disposition_to_recommendation(
        "",
        "outpatient_appointment",
        "Receiving service guidelines matched.",
    )
    assert combined == (
        "**Advisory SPoA disposition:** Outpatient appointment.\n"
        "_Receiving service guidelines matched._"
    )
