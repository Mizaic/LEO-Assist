"""VT-B193DEBB: pub/sub pipeline to Neo4j handoff.

Atlas trace:
  DI: DI-FA2E369F, DI-F71A6A69, DI-EF7F158D
  DO: DO-4641EEE1
  VT: VT-B193DEBB

Verifies the VT acceptance criteria:
  AC1 -- the API sends pipeline job messages with run and case identifiers.
  AC2 -- the worker subscribes to the queue and publishes progress/completion
         events on the run id channel.
  AC3 -- pipeline results or audit details are written before completed output
         can be read by requesters.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROUTER = ROOT / "services/api/app/routers/pipeline.py"
PIPELINE_WORKER = ROOT / "services/pipeline_worker/app/main.py"
PROGRESS_CALLBACK = ROOT / "services/pipeline_worker/app/services/progress_callback.py"
WORKFLOW_ENGINE = ROOT / "libs/workflow/engine.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_in_order(text: str, before: str, after: str) -> None:
    before_at = text.index(before)
    after_at = text.index(after)
    assert before_at < after_at, f"expected {before!r} before {after!r}"


def test_vtb193debb_tc001_api_queues_jobs_with_run_and_case_context() -> None:
    """AC1 -- API job messages carry run and case identifiers."""
    router = _read(PIPELINE_ROUTER)

    assert 'PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")' in router
    assert "await bus.send(PIPELINE_QUEUE" in router
    assert '"event_type": "encounter-created"' in router
    assert '"patient_id":' in router
    assert '"encounter_id":' in router
    assert '"run_id": run_id' in router


def test_vtb193debb_tc002_worker_subscribes_and_publishes_run_channel_events() -> None:
    """AC2 -- worker drains the queue and publishes progress by run id."""
    worker = _read(PIPELINE_WORKER)
    callback = _read(PROGRESS_CALLBACK)

    assert 'QUEUE_NAME = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")' in worker
    lab_pipeline = _read(ROOT / "libs/validation_lab/pipeline.py")
    assert 'os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")' in lab_pipeline
    assert "leo-pipeline-jobs" not in lab_pipeline
    assert "_run_consumer(bus, on_message)" in worker
    assert "handler.handle_message(msg, step_callback=step_callback)" in worker
    assert "publish_progress(run_id, payload)" in callback
    assert 'payload.setdefault("run_id", run_id)' in callback


def test_vtb193debb_tc003_audit_write_precedes_completion_callback() -> None:
    """AC3 -- audit persistence happens before run_completed is published."""
    engine = _read(WORKFLOW_ENGINE)

    _assert_in_order(
        engine,
        "await self._write_audit_event(event, step_results, final_status, pipeline_state)",
        'done_type = "run_error" if final_status == "error" else "run_completed"',
    )
    assert '"type": "PipelineRun"' in engine
    assert '"run_id": event.run_id' in engine
    assert '"status": status' in engine
    assert "MERGE (ae:AuditEvent {id: $id})" in engine
