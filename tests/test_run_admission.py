"""Tests for deterministic pipeline run admission (D1.1)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore
from libs.workflow.run_admission import build_admission_key


def _body(run_id: str = "run-admit-1") -> dict:
    return {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": run_id,
        "patient_id": "p-admit-1",
        "referral_id": "ref-1",
        "chunk_ids": ["chunk-a", "chunk-b"],
    }


def test_admission_key_changes_when_chunk_order_changes() -> None:
    first = build_admission_key(
        {
            "patient_id": "p-1",
            "plan_definition_id": "pd-referral-assessment",
            "chunk_ids": ["a", "b"],
        }
    )
    second = build_admission_key(
        {
            "patient_id": "p-1",
            "plan_definition_id": "pd-referral-assessment",
            "chunk_ids": ["b", "a"],
        }
    )
    assert first != second


def test_admission_key_stable_for_identical_input() -> None:
    body = _body()
    assert build_admission_key(body) == build_admission_key(dict(body))


def test_validation_lab_admission_key_includes_run_id() -> None:
    """Re-Test on the same case must not collide with a prior Lab PipelineRun."""
    base = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "patient_id": "p-lab-1",
        "referral_id": "ref-lab-1",
        "chunk_ids": ["chunk-a"],
        "context": {"source": "validation-lab", "case_id": "case-1"},
    }
    first = build_admission_key({**base, "run_id": "lab-run-1"})
    second = build_admission_key({**base, "run_id": "lab-run-2"})
    prod = build_admission_key(
        {
            **base,
            "run_id": "lab-run-1",
            "context": {"source": "production", "case_id": "case-1"},
        }
    )
    assert first != second
    assert first != prod


class _AdmissionClient:
    """Minimal in-memory client for run admission races."""

    def __init__(self) -> None:
        self.runs_by_key: dict[str, dict] = {}
        self.runs_by_id: dict[str, dict] = {}

    def run(self, query: str, **params):  # noqa: ANN001
        from libs.cypher.pipeline_stage_queries import (
            ADMIT_PIPELINE_RUN,
            CLAIM_FIRST_STEP_ENQUEUE,
            ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT,
            ENSURE_PIPELINE_RUN_CONSTRAINT,
            ENSURE_PIPELINE_STAGE_CONSTRAINT,
        )

        if query in (
            ENSURE_PIPELINE_RUN_CONSTRAINT,
            ENSURE_PIPELINE_RUN_ADMISSION_KEY_CONSTRAINT,
            ENSURE_PIPELINE_STAGE_CONSTRAINT,
        ):
            return []
        if query == ADMIT_PIPELINE_RUN:
            key = params["admission_key"]
            existing = self.runs_by_key.get(key)
            if existing is None:
                row = {
                    "id": params["run_id"],
                    "admission_key": key,
                    "first_step_enqueued": False,
                    "status": "running",
                }
                self.runs_by_key[key] = row
                self.runs_by_id[row["id"]] = row
                return [
                    {
                        "run_id": row["id"],
                        "created": True,
                        "first_step_enqueued": False,
                        "status": "running",
                    }
                ]
            return [
                {
                    "run_id": existing["id"],
                    "created": False,
                    "first_step_enqueued": existing["first_step_enqueued"],
                    "status": existing["status"],
                }
            ]
        if query == CLAIM_FIRST_STEP_ENQUEUE:
            run = self.runs_by_id.get(params["run_id"])
            if run is None or run["first_step_enqueued"]:
                return [{"enqueued": False}]
            run["first_step_enqueued"] = True
            return [{"enqueued": True}]
        raise ValueError(f"unsupported query: {query[:40]}")


def _request(run_id: str) -> StepRequest:
    return StepRequest.from_message({**_body(run_id), "run_id": run_id})


def test_concurrent_admissions_return_one_created_run() -> None:
    client = _AdmissionClient()
    store = PipelineStageStore(client)
    key = build_admission_key(_body("run-a"))

    def _admit(run_id: str) -> tuple[bool, str]:
        result = store.admit_run(_request(run_id), admission_key=key)
        return result.created, result.run_id

    run_ids = [f"run-{i}" for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_admit, run_id) for run_id in run_ids]
        outcomes = [f.result() for f in as_completed(futures)]

    created = [item for item in outcomes if item[0]]
    assert len(created) == 1
    assert len({item[1] for item in outcomes}) == 1


def test_first_step_enqueue_is_single_flight() -> None:
    client = _AdmissionClient()
    store = PipelineStageStore(client)
    key = build_admission_key(_body("run-enq"))
    admission = store.admit_run(_request("run-enq"), admission_key=key)
    assert store.claim_first_step_enqueue(admission.run_id) is True
    assert store.claim_first_step_enqueue(admission.run_id) is False
