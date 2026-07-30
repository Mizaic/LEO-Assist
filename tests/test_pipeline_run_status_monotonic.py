"""D1.3 -- monotonic PipelineRun status (no terminal -> running regression)."""

from __future__ import annotations

from libs.cypher.pipeline_stage_queries import ADMIT_PIPELINE_RUN, UPSERT_PIPELINE_RUN
from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore

_TERMINAL = ("completed", "failed", "cancelled", "poisoned")


class _MonotonicRunClient:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.runs_by_key: dict[str, dict] = {}

    def run(self, query: str, **params):  # noqa: ANN001
        if query == UPSERT_PIPELINE_RUN:
            run_id = params["run_id"]
            existing = self.runs.get(run_id, {})
            current = str(existing.get("status") or "running")
            requested = str(params["status"])
            if current in _TERMINAL and requested == "running":
                new_status = current
            else:
                new_status = requested
            row = {**params, "status": new_status}
            self.runs[run_id] = row
            return [{"id": run_id, "status": new_status}]
        if query == ADMIT_PIPELINE_RUN:
            key = params["admission_key"]
            run_id = params["run_id"]
            by_key = self.runs_by_key.get(key)
            by_id = self.runs.get(run_id)
            if by_key is not None:
                existing = by_key
            elif by_id is not None:
                if by_id.get("admission_key") is None:
                    by_id["admission_key"] = key
                    self.runs_by_key[key] = by_id
                existing = by_id
            else:
                existing = {
                    "id": run_id,
                    "admission_key": key,
                    "status": "running",
                    "first_step_enqueued": False,
                }
                self.runs_by_key[key] = existing
                self.runs[run_id] = existing
            return [
                {
                    "run_id": existing["id"],
                    "created": existing["id"] == run_id,
                    "first_step_enqueued": existing["first_step_enqueued"],
                    "status": existing["status"],
                }
            ]
        raise ValueError(f"unsupported query: {query[:40]}")


def _request(run_id: str = "run-mono-1") -> StepRequest:
    return StepRequest(
        event_type="referral-received",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        plan_definition_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-mono-1",
    )


def test_upsert_run_does_not_regress_completed_to_running() -> None:
    client = _MonotonicRunClient()
    store = PipelineStageStore(client)
    request = _request()
    store.upsert_run(request, status="completed")
    store.upsert_run(request, status="running")
    assert client.runs[request.run_id]["status"] == "completed"


def test_upsert_run_allows_failed_to_completed() -> None:
    client = _MonotonicRunClient()
    store = PipelineStageStore(client)
    request = _request("run-mono-2")
    store.upsert_run(request, status="failed")
    store.upsert_run(request, status="completed")
    assert client.runs[request.run_id]["status"] == "completed"


def test_admit_preserves_terminal_status_on_match() -> None:
    client = _MonotonicRunClient()
    store = PipelineStageStore(client)
    key = "admission-key-terminal"
    first = store.admit_run(_request("run-mono-3"), admission_key=key)
    client.runs[first.run_id]["status"] = "completed"
    client.runs_by_key[key]["status"] = "completed"
    second = store.admit_run(_request("run-mono-other"), admission_key=key)
    assert second.created is False
    assert second.status == "completed"
