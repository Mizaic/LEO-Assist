"""Unit tests for action-already-done filtering.

Atlas trace: DI-B3B44F09
"""

from __future__ import annotations

from libs.guidelines.action_already_done import (
    action_already_done,
    all_actions_already_done,
    apply_already_done_filter,
    is_referral_action,
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
