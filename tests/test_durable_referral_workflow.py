from pathlib import Path

from libs.workflow.durable_steps import StepRequest
from scripts.seed_plan_definitions import PLAN_DEFINITIONS
from services.pipeline_worker.app.services.referral_durable_steps import REFERRAL_STEPS


def _referral_plan() -> dict:
    for plan in PLAN_DEFINITIONS:
        if plan.get("id") == "pd-referral-assessment":
            return plan
    raise AssertionError("pd-referral-assessment seed not found")


def test_referral_plan_declares_durable_pubsub_metadata():
    plan = _referral_plan()

    assert plan["_workflowMode"] == "durable_pubsub"
    assert len(plan["_durableSteps"]) >= 10
    for step in plan["_durableSteps"]:
        assert step["event_type"]
        assert step["loads"]
        assert step["persists"]
        assert step["idempotency_key"] == "run_id:step_id"


def test_referral_plan_does_not_use_legacy_sbar_subgraph():
    plan = _referral_plan()

    assert all(action.get("_subgraphId") != "sbar" for action in plan.get("action", []))
    assert "sbar" in plan.get("_deprecatedSubgraphs", [])
    assert not Path("libs/pipeline_graph/subgraphs/sbar.py").exists()


def test_referral_plan_persists_clinical_facts_before_sbar():
    plan = _referral_plan()
    ordered = sorted(plan["action"], key=lambda action: action.get("_sequence", 0))
    events = [action.get("_durableEventType") for action in ordered]

    assert events.index("clinical_facts_persist_requested") < events.index(
        "sbar_requested"
    )


def test_referral_durable_registry_declares_loads_persists_and_chain():
    events = [step.event_type for step in REFERRAL_STEPS]

    assert events[0] == "extraction_requested"
    assert events[-1] == "human_review_requested"
    for step in REFERRAL_STEPS:
        assert step.loads
        assert step.persists
        if step.next_event_type:
            assert step.next_step_id


def test_step_request_round_trips_next_message_scope():
    request = StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "durable-ref-extraction",
            "patient_id": "p1",
            "encounter_id": "e1",
            "guideline_id": "NG12",
            "context": {"completeness_domain": "cancer_referrals"},
        }
    )

    next_body = request.to_message(
        "post_processing_requested", "durable-ref-post-processing"
    )

    assert next_body["event_type"] == "post_processing_requested"
    assert next_body["step_id"] == "durable-ref-post-processing"
    assert next_body["run_id"] == "run-1"
    assert next_body["patient_id"] == "p1"
    assert next_body["guideline_id"] == "NG12"
