"""Unit tests for action-already-done filtering.

Atlas trace: DI-B3B44F09
"""

from __future__ import annotations

from libs.guidelines.action_already_done import (
    action_already_done,
    all_actions_already_done,
    apply_already_done_filter,
    is_referral_action,
    mark_already_done_actions,
    split_already_actioned_rules,
)
from libs.guidelines.investigation_family import (
    FIT_KIT_PROCEDURE_ID,
    FIT_RESULT_OBSERVABLE_ID,
)


FIT_KIT_ACTION = {
    "concept_id": FIT_KIT_PROCEDURE_ID,
    "name": "Provision of faecal immunochemical test kit (procedure)",
    "strength": "offer",
}
REFERRAL_ACTION = {
    "concept_id": "268338007",
    "name": "Fast track referral for suspected colorectal cancer (procedure)",
    "strength": "refer",
}
CHEST_XRAY_ACTION = {
    "concept_id": "168731009",
    "name": "Plain X-ray of chest (procedure)",
    "strength": "offer",
}
PELVIC_US_ACTION = {
    "concept_id": "418394000",
    "name": "Ultrasound scan of abdomen and pelvis (procedure)",
    "strength": "offer",
}
PELVIC_US_FAMILY = {"418394000", "24848001", "426491001", "447801003"}


def test_fit_result_stops_fit_kit_action() -> None:
    observations = [{"observable_id": FIT_RESULT_OBSERVABLE_ID, "value": 126.0}]
    assert action_already_done(FIT_KIT_ACTION, [], observations) is True


def test_fit_finding_code_stops_fit_kit_action() -> None:
    assert action_already_done(FIT_KIT_ACTION, ["1101371000000105"], []) is True


def test_referral_action_is_not_dropped() -> None:
    assert is_referral_action(REFERRAL_ACTION) is True
    assert (
        action_already_done(REFERRAL_ACTION, [REFERRAL_ACTION["concept_id"]], [])
        is False
    )


def test_rule_with_only_fit_kit_is_dropped() -> None:
    payload = {
        "rule_id": "1.3.1",
        "actions": [FIT_KIT_ACTION],
        "action": FIT_KIT_ACTION,
    }
    observations = [{"observable_id": FIT_RESULT_OBSERVABLE_ID, "value": 126.0}]
    assert apply_already_done_filter(payload, [], observations) is None
    assert all_actions_already_done(payload, [], observations) is True


def test_mark_keeps_completed_action_and_flags_it() -> None:
    """DI-B3B44F09: completed actions stay on the rule, marked already_done."""
    payload = {
        "rule_id": "1.5.2",
        "actions": [dict(FIT_KIT_ACTION)],
        "action": dict(FIT_KIT_ACTION),
    }
    observations = [{"observable_id": FIT_RESULT_OBSERVABLE_ID, "value": 126.0}]
    marked = mark_already_done_actions(payload, [], observations)
    assert marked is not None
    assert marked["already_actioned"] is True
    assert marked["actions"][0]["already_done"] is True
    assert marked["actions"][0]["name"] == FIT_KIT_ACTION["name"]


def test_mark_leaves_outstanding_action_uncrossed() -> None:
    payload = {
        "rule_id": "1.5.2",
        "actions": [dict(CHEST_XRAY_ACTION)],
        "action": dict(CHEST_XRAY_ACTION),
    }
    marked = mark_already_done_actions(payload, [], [])
    assert marked["already_actioned"] is False
    assert marked["actions"][0]["already_done"] is False


def test_mark_mixed_rule_crosses_only_completed_action() -> None:
    payload = {
        "rule_id": "mixed",
        "actions": [dict(FIT_KIT_ACTION), dict(REFERRAL_ACTION)],
        "action": dict(FIT_KIT_ACTION),
    }
    observations = [{"observable_id": FIT_RESULT_OBSERVABLE_ID, "value": 80.0}]
    marked = mark_already_done_actions(payload, [], observations)
    assert marked["already_actioned"] is False
    by_name = {item["name"]: item["already_done"] for item in marked["actions"]}
    assert by_name[FIT_KIT_ACTION["name"]] is True
    assert by_name[REFERRAL_ACTION["name"]] is False


def test_split_already_actioned_rules_peels_completed() -> None:
    open_rule = {"rule_id": "1.5.14", "already_actioned": False}
    done_rule = {"rule_id": "1.5.2", "already_actioned": True}
    open_rules, done_rules = split_already_actioned_rules([open_rule, done_rule])
    assert [rule["rule_id"] for rule in open_rules] == ["1.5.14"]
    assert [rule["rule_id"] for rule in done_rules] == ["1.5.2"]


def test_finding_that_interprets_procedure_counts_as_done() -> None:
    finding_id = "finding-of-chest-xray"
    observable_id = "obs-chest-xray"

    def related_lookup(concept_id: str) -> dict:
        if concept_id == finding_id:
            return {"interprets_observables": [{"id": observable_id}]}
        if concept_id == observable_id:
            return {
                "component_of_procedures": [{"id": CHEST_XRAY_ACTION["concept_id"]}]
            }
        if concept_id == CHEST_XRAY_ACTION["concept_id"]:
            return {"has_components": [{"id": observable_id}]}
        return {}

    assert (
        action_already_done(
            CHEST_XRAY_ACTION,
            [finding_id],
            [],
            related_lookup=related_lookup,
        )
        is True
    )


def test_catalog_family_marks_pelvic_us_variants_already_done() -> None:
    """Family members come from InvestigationFamily, not a Python list."""
    families = {"418394000": set(PELVIC_US_FAMILY)}
    assert (
        action_already_done(PELVIC_US_ACTION, ["447801003"], [], families=families)
        is True
    )
    assert (
        action_already_done(PELVIC_US_ACTION, ["24848001"], [], families=families)
        is True
    )
    assert (
        action_already_done(PELVIC_US_ACTION, ["426491001"], [], families=families)
        is True
    )


def test_pelvic_us_variant_is_not_done_without_catalog() -> None:
    assert action_already_done(PELVIC_US_ACTION, ["24848001"], []) is False


def test_unrelated_finding_does_not_mark_pelvic_us_done() -> None:
    families = {"418394000": set(PELVIC_US_FAMILY)}
    assert (
        action_already_done(PELVIC_US_ACTION, ["73211009"], [], families=families)
        is False
    )


def test_unrelated_finding_does_not_count_as_done() -> None:
    def related_lookup(concept_id: str) -> dict:
        return {}

    assert (
        action_already_done(
            CHEST_XRAY_ACTION,
            ["unrelated-finding"],
            [],
            related_lookup=related_lookup,
        )
        is False
    )
