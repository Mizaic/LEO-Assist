from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libs.pipeline.document_chunk_loader import DOCUMENT_CHUNKS_MODE
from libs.workflow.durable_steps import StepRequest
from scripts.seed_plan_definitions import PLAN_DEFINITIONS

# Legacy hard-coded referral step registry was removed in favour of
# DurableStepRunner + PlanDefinition relatedActions. Keep these imports
# optional so seed-structure tests still run.
try:
    from services.pipeline_worker.app.services.referral_durable_steps import (
        REFERRAL_STEP_BY_EVENT,
        REFERRAL_STEPS,
        _apply_referral_handoff_fields,
        _load_step_state,
    )

    _HAS_REFERRAL_STEPS = True
except ImportError:  # pragma: no cover - module retired
    REFERRAL_STEP_BY_EVENT = {}
    REFERRAL_STEPS = ()
    _apply_referral_handoff_fields = None
    _load_step_state = None
    _HAS_REFERRAL_STEPS = False

_skip_missing_referral_steps = pytest.mark.skipif(
    not _HAS_REFERRAL_STEPS,
    reason="referral_durable_steps removed; DurableStepRunner owns the chain",
)


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


def test_referral_plan_sbar_action_is_graph_backed_orchestrator_step():
    """Canvas may keep subgraph id 'sbar' (SBAROrchestrator wrapper) but must
    declare the durable sbar_requested event and retire in-memory SBAR."""
    plan = _referral_plan()

    sbar_actions = [
        a for a in plan.get("action", []) if a.get("_subgraphId") == "sbar"
    ]
    assert len(sbar_actions) == 1
    assert sbar_actions[0].get("_durableEventType") == "sbar_requested"
    assert "legacy_sbar_in_memory" in plan.get("_deprecatedSubgraphs", [])
    assert Path("libs/pipeline_graph/subgraphs/sbar.py").exists()


def test_referral_plan_persists_clinical_facts_before_sbar():
    plan = _referral_plan()
    ordered = sorted(plan["action"], key=lambda action: action.get("_sequence", 0))
    events = [action.get("_durableEventType") for action in ordered]

    assert events.index("clinical_facts_persist_requested") < events.index(
        "sbar_requested"
    )


def test_referral_plan_actions_declare_durable_event_types():
    plan = _referral_plan()
    for action in plan.get("action", []):
        assert action.get("_durableEventType"), (
            f"Action '{action.get('id')}' is missing _durableEventType"
        )


@_skip_missing_referral_steps
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


@_skip_missing_referral_steps
def test_apply_referral_handoff_fields_promotes_document_chunks_from_nested_context() -> None:
    state: dict = {}
    handoff = {
        "chunk_ids": ["chunk-a", "chunk-b"],
        "document_reference_id": "000049831707:leo-referral-bundle",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "referral_id": "000049831707",
        "ubrn": "000049831707",
    }
    request = StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "durable-ref-extraction",
            "patient_id": "9728344880",
            "encounter_id": "000049831707:referral-assessment",
            "context": {"source": "hccp_referral_prep", **handoff},
        }
    )
    body = {
        "event_type": "extraction_requested",
        "run_id": "run-1",
        "workflow_id": "pd-referral-assessment",
        "plan_definition_id": "pd-referral-assessment",
        "step_id": "durable-ref-extraction",
        "patient_id": "9728344880",
        "encounter_id": "000049831707:referral-assessment",
        "context": {"source": "hccp_referral_prep", **handoff},
    }

    _apply_referral_handoff_fields(state, request, body)

    assert state["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE
    assert state["chunk_ids"] == ["chunk-a", "chunk-b"]
    assert state["document_reference_id"] == "000049831707:leo-referral-bundle"
    assert state["referral_id"] == "000049831707"
    assert state["ubrn"] == "000049831707"


@_skip_missing_referral_steps
def test_apply_referral_handoff_fields_promotes_document_chunks_from_body() -> None:
    state: dict = {}
    request = StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "durable-ref-extraction",
            "patient_id": "9728344880",
            "encounter_id": "000049831707:referral-assessment",
            "context": {"source": "hccp_referral_prep"},
        }
    )
    body = {
        "chunk_ids": ["chunk-a", "chunk-b"],
        "document_reference_id": "000049831707:leo-referral-bundle",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "context": {"ubrn": "000049831707"},
    }

    _apply_referral_handoff_fields(state, request, body)

    assert state["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE
    assert state["chunk_ids"] == ["chunk-a", "chunk-b"]
    assert state["document_reference_id"] == "000049831707:leo-referral-bundle"
    assert state["ubrn"] == "000049831707"


@_skip_missing_referral_steps
def test_load_step_state_loads_document_chunks_instead_of_encounter() -> None:
    definition = REFERRAL_STEP_BY_EVENT["extraction_requested"]
    body = {
        "event_type": "extraction_requested",
        "run_id": "run-1",
        "plan_definition_id": "pd-referral-assessment",
        "workflow_id": "pd-referral-assessment",
        "step_id": "durable-ref-extraction",
        "patient_id": "9728344880",
        "encounter_id": "000049831707:referral-assessment",
        "chunk_ids": ["chunk-a", "chunk-b"],
        "document_reference_id": "000049831707:leo-referral-bundle",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "context": {"ubrn": "000049831707"},
    }
    request = StepRequest.from_message(body)

    chunk_rows = [
        {
            "chunk_id": "chunk-a",
            "text": "Referral text A",
            "ordinal": 0,
            "char_start": 0,
            "char_end": 15,
        },
        {
            "chunk_id": "chunk-b",
            "text": "Referral text B",
            "ordinal": 1,
            "char_start": 17,
            "char_end": 32,
        },
    ]

    def mock_run(query: str, **kwargs):
        if "UNWIND $chunk_ids" in query:
            return chunk_rows
        if "Encounter" in query:
            return [{"text": "encounter fallback"}]
        return []

    client = MagicMock()
    client.run.side_effect = mock_run
    store = MagicMock()
    store.load_accumulated_state.return_value = {}

    loaded = _load_step_state(client, store, request, definition, body=body)

    assert loaded["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE
    assert loaded["source_node_type"] == "Chunk"
    assert loaded["source_node_id"] == "000049831707:leo-referral-bundle"
    assert len(loaded["sentences"]) == 2
    assert loaded["encounter_text"]
    encounter_queries = [
        call.args[0]
        for call in client.run.call_args_list
        if call.args and "Encounter" in call.args[0]
    ]
    assert encounter_queries == []
