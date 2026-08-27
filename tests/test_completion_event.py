"""Minimal Service Bus completion event payload for durable pipelines."""

from __future__ import annotations

from libs.workflow.completion_event import build_completion_event_body
from libs.workflow.durable_steps import StepRequest, StepResult

_CLINICAL_SBAR_OUTPUT = {
    "sbar_assessment_id": "assess-xyz",
    "sbar_sections": {
        "situation": "Patient has abdominal pain.",
        "background": "Previous GP visit noted.",
        "assessment": "Possible upper GI referral.",
        "recommendation": "Refer under 2WW.",
    },
    "sbar_report": {
        "situation": "Patient has abdominal pain.",
        "background": "Previous GP visit noted.",
        "assessment": "Possible upper GI referral.",
        "recommendation": "Refer under 2WW.",
        "assessment_id": "assess-xyz",
        "actions": [{"label": "Refer"}],
        "rules": [{"id": "r1"}],
    },
}


def _request(**overrides: object) -> StepRequest:
    body = {
        "event_type": "durable_step",
        "run_id": "run-pubsub-1",
        "workflow_id": "pd-referral-assessment",
        "step_id": "act-ref-sbar",
        "patient_id": "patient-1",
        "encounter_id": "enc-1",
        "context": {"ubrn": "000481914514", "case_id": "upper_gi_form_001"},
    }
    body.update(overrides)
    return StepRequest.from_message(body)


def test_completion_event_carries_run_id_ubrn_and_assessment_id() -> None:
    body = build_completion_event_body(
        event_type="referral_assessment_completed",
        request=_request(),
        result=StepResult(status="completed", output=dict(_CLINICAL_SBAR_OUTPUT)),
    )
    assert body == {
        "event_type": "referral_assessment_completed",
        "run_id": "run-pubsub-1",
        "ubrn": "000481914514",
        "assessment_id": "assess-xyz",
    }


def test_completion_event_omits_clinical_and_patient_fields() -> None:
    body = build_completion_event_body(
        event_type="referral_assessment_completed",
        request=_request(),
        result=StepResult(status="completed", output=dict(_CLINICAL_SBAR_OUTPUT)),
    )
    forbidden = {
        "patient_id",
        "encounter_id",
        "context",
        "errors",
        "sbar_sections",
        "sbar_report",
        "sbar_assessment_id",
        "workflow_id",
        "plan_definition_id",
    }
    assert forbidden.isdisjoint(body.keys())
    assert "abdominal pain" not in str(body)


def test_completion_event_omits_empty_optional_fields() -> None:
    body = build_completion_event_body(
        event_type="referral_assessment_completed",
        request=_request(context={}),
        result=StepResult(status="completed", output={}),
    )
    assert body == {
        "event_type": "referral_assessment_completed",
        "run_id": "run-pubsub-1",
    }
