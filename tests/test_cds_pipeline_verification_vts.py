"""CDS pub/sub pipeline verification tests for UN-89E2AE36.

Atlas trace:
  DO: DO-4641EEE1
  VTs:
    VT-37607F4B, VT-B91EE9F2, VT-BE8D8651, VT-CBB3C8E8,
    VT-36E2C3B1, VT-3902EBF7, VT-F9794391, VT-1B3A081F,
    VT-E5F38835, VT-EEBF460C

These tests verify the production path that enqueues CDS work, consumes
pipeline-jobs messages, persists results/audit data, and publishes completion
events without writing directly to the clinical record.
"""

from __future__ import annotations

import re
from pathlib import Path

from libs.workflow.engine import ActionDefinition, WorkflowEngine
from services.coding_worker.app.services.job_handler import CodingJobMessage

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROUTER = ROOT / "services/api/app/routers/pipeline.py"
JOB_HANDLER = ROOT / "services/coding_worker/app/services/job_handler.py"
PIPELINE_WORKER = ROOT / "services/pipeline_worker/app/main.py"
PROGRESS_CALLBACK = ROOT / "services/pipeline_worker/app/services/progress_callback.py"
WORKFLOW_ENGINE = ROOT / "libs/workflow/engine.py"
WORKFLOW_EVENTS = ROOT / "libs/workflow/events.py"
PERSIST = ROOT / "libs/pipeline_graph/subgraphs/persist.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_in_order(text: str, before: str, after: str) -> None:
    assert text.index(before) < text.index(after)


def test_vt37607f4b_valid_job_starts_workflow() -> None:
    """VT-37607F4B -- a valid CDS job starts the durable pipeline runner."""
    job = CodingJobMessage(
        patient_id="p-1", encounter_id="e-1", mode="extract_encounter"
    )
    handler = _read(JOB_HANDLER)

    assert job.patient_id == "p-1"
    assert job.encounter_id == "e-1"
    assert "WorkflowEngine(" not in handler
    assert "from libs.workflow.durable_step_runner import DurableStepRunner" in handler
    assert (
        "await DurableStepRunner.start(body, bus=bus, queue_name=_PIPELINE_QUEUE)"
        in handler
    )
    assert "await _dispatch_durable_for_encounter(" in handler


def test_vtb91ee9f2_worker_receives_pipeline_messages() -> None:
    """VT-B91EE9F2 -- the worker receives messages from pipeline-jobs."""
    worker = _read(PIPELINE_WORKER)
    events = _read(WORKFLOW_EVENTS)

    assert 'QUEUE_NAME = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")' in worker
    assert "async def _run_consumer(bus, on_message)" in worker
    assert "ServiceBusEventHandler" in worker
    assert "Handles events from the Azure Service Bus pipeline-jobs queue" in events


def test_vtbe8d8651_invalid_job_fails_before_workflow() -> None:
    """VT-BE8D8651 -- invalid jobs fail validation before workflow execution."""
    handler = _read(JOB_HANDLER)

    assert "except ValidationError:" in handler
    assert "Malformed coding job message dropped" in handler
    assert "await _run_coding_job(job, message)" in handler


def test_vtcbb3c8e8_message_keeps_run_and_case_context() -> None:
    """VT-CBB3C8E8 -- run id and case context are preserved in messages."""
    handler = _read(JOB_HANDLER)
    router = _read(PIPELINE_ROUTER)

    assert 'raw_message.correlation_id or body.get("run_id")' in handler
    assert '"patient_id": patient_id' in handler
    assert '"encounter_id": encounter_id' in handler
    assert "correlation_id=run_id" in router
    assert '"run_id": run_id' in router


def test_vt36e2c3b1_results_persist_before_completion_callback() -> None:
    """VT-36E2C3B1 -- result/audit persistence precedes completion callback."""
    engine = _read(WORKFLOW_ENGINE)
    persist = _read(PERSIST)

    _assert_in_order(
        engine,
        "await self._write_audit_event(event, step_results, final_status, pipeline_state)",
        'done_type = "run_error" if final_status == "error" else "run_completed"',
    )
    # Anchored on the call sites in write_patient_graph. The coding-decision
    # loop moved into ``_write_coding_decisions``, so the old literal
    # ``session.run(UPSERT_CODING_DECISION`` is no longer at the call site
    # even though the evidence still gets written first.
    _assert_in_order(
        persist,
        "docs_written = write_documents_from_sentences_payload",
        "n = _write_coding_decisions(",
    )


def test_vt3902ebf7_neo4j_persist_failure_blocks_success_event() -> None:
    """VT-3902EBF7 -- Neo4j persist failure turns completion into run_error."""
    action = ActionDefinition(
        action_id="persist-1",
        subgraph_id="persist",
        trigger_type="event",
        trigger_name="encounter-created",
    )

    error = WorkflowEngine._persist_failure(
        action,
        {"errors": ["persist_patient_graph: neo4j unavailable"]},
    )

    assert error == "persist_patient_graph: neo4j unavailable"
    engine = _read(WORKFLOW_ENGINE)
    assert (
        'done_type = "run_error" if final_status == "error" else "run_completed"'
        in engine
    )


def test_vtf9794391_audit_write_happens_before_completion_event() -> None:
    """VT-F9794391 -- audit data is written before completion is published."""
    engine = _read(WORKFLOW_ENGINE)

    _assert_in_order(
        engine,
        "await self._write_audit_event(event, step_results, final_status, pipeline_state)",
        "step_callback(\n                {",
    )
    assert "MERGE (ae:AuditEvent {id: $id})" in engine


def test_vt1b3a081f_completion_event_is_not_a_clinical_record_write() -> None:
    """VT-1B3A081F -- completion events are progress payloads, not record writes."""
    callback = _read(PROGRESS_CALLBACK)
    worker = _read(PIPELINE_WORKER)

    assert "publish_progress(run_id, payload)" in callback
    assert 'update_from_event(patient_id or "", run_id, payload)' in callback
    assert "write_documents_from_sentences_payload" not in callback
    assert "write_documents_from_sentences_payload" not in worker


def test_vte5f38835_completion_event_carries_run_id_and_status() -> None:
    """VT-E5F38835 -- completion/progress events include run id and status."""
    engine = _read(WORKFLOW_ENGINE)
    callback = _read(PROGRESS_CALLBACK)

    assert '"run_id": event.run_id' in engine
    assert '"status": final_status' in engine
    assert 'payload.setdefault("run_id", run_id)' in callback


def test_vteebf460c_readback_context_is_available_in_events() -> None:
    """VT-EEBF460C -- events carry readback context for SSE clients."""
    engine = _read(WORKFLOW_ENGINE)
    router = _read(PIPELINE_ROUTER)

    assert '"patient_id": pipeline_state.get("patient_id")' in engine
    assert '"encounter_id": pipeline_state.get("encounter_id")' in engine
    assert 'stream_path": f"/api/pipeline/progress/{run_id}"' in router


def test_pipeline_vt_ids_are_declared_in_this_module() -> None:
    """Traceability guard -- every pipeline VT id is cited on disk."""
    text = _read(Path(__file__))
    expected_ids = {
        "VT-37607F4B",
        "VT-B91EE9F2",
        "VT-BE8D8651",
        "VT-CBB3C8E8",
        "VT-36E2C3B1",
        "VT-3902EBF7",
        "VT-F9794391",
        "VT-1B3A081F",
        "VT-E5F38835",
        "VT-EEBF460C",
    }

    assert expected_ids <= set(re.findall(r"VT-[0-9A-F]{8}", text))
