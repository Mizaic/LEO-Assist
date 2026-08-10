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


def test_patient_viewer_admission_key_includes_run_id() -> None:
    """Care reprocess runs must not reuse a prior failed PipelineRun."""
    base = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "patient_id": "9728344007",
        "referral_id": "000049823847",
        "chunk_ids": ["chunk-a"],
        "context": {
            "source": "patient-viewer",
            "referral_id": "000049823847",
            "document_reference_id": "DocumentReference-151066",
        },
    }
    first = build_admission_key({**base, "run_id": "run-one"})
    second = build_admission_key({**base, "run_id": "run-two"})
    assert first != second


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
        from libs.cypher.pipeline_stage_queries import ADMIT_VALIDATION_LAB_PIPELINE_RUN

        if query in (ADMIT_PIPELINE_RUN, ADMIT_VALIDATION_LAB_PIPELINE_RUN):
            if query == ADMIT_VALIDATION_LAB_PIPELINE_RUN:
                run_id = params["run_id"]
                key = params["admission_key"]
                existing = self.runs_by_id.get(run_id)
                if existing is None:
                    existing = {
                        "id": run_id,
                        "admission_key": key,
                        "first_step_enqueued": False,
                        "status": "running",
                    }
                    self.runs_by_id[run_id] = existing
                    self.runs_by_key[key] = existing
                return [
                    {
                        "run_id": existing["id"],
                        "created": False,
                        "first_step_enqueued": existing["first_step_enqueued"],
                        "status": existing["status"],
                    }
                ]
            key = params["admission_key"]
            run_id = params["run_id"]
            by_key = self.runs_by_key.get(key)
            by_id = self.runs_by_id.get(run_id)
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
                    "first_step_enqueued": False,
                    "status": "running",
                }
                self.runs_by_key[key] = existing
                self.runs_by_id[run_id] = existing
            return [
                {
                    "run_id": existing["id"],
                    "created": existing["id"] == run_id,
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


def test_admit_reuses_existing_run_id_with_null_admission_key() -> None:
    """Null-key upsert runs must be reused, not re-created, on redelivery."""
    client = _AdmissionClient()
    store = PipelineStageStore(client)
    run_id = "run-null-key"
    client.runs_by_id[run_id] = {
        "id": run_id,
        "admission_key": None,
        "first_step_enqueued": True,
        "status": "completed",
    }
    key = build_admission_key(_body(run_id))
    result = store.admit_run(_request(run_id), admission_key=key)
    assert result.run_id == run_id
    assert result.created is True
    assert result.status == "completed"
    assert result.first_step_enqueued is True
    assert client.runs_by_id[run_id]["admission_key"] == key
    assert client.runs_by_key[key]["id"] == run_id


def test_validation_lab_admit_creates_run_by_lab_run_id() -> None:
    """Lab runs must not reuse an older PipelineRun via admission_key."""
    client = _AdmissionClient()
    store = PipelineStageStore(client)
    shared_key = build_admission_key(_body("old-run"))
    client.runs_by_key[shared_key] = {
        "id": "old-run",
        "admission_key": shared_key,
        "first_step_enqueued": True,
        "status": "completed",
    }
    client.runs_by_id["old-run"] = client.runs_by_key[shared_key]
    lab_body = {
        **_body("lab-run-new"),
        "context": {"source": "validation-lab", "case_id": "case-1"},
    }
    result = store.admit_run(
        StepRequest.from_message(lab_body),
        admission_key=build_admission_key(lab_body),
    )
    assert result.run_id == "lab-run-new"
    assert client.runs_by_id["lab-run-new"]["id"] == "lab-run-new"


def test_patient_viewer_admit_creates_run_by_run_id() -> None:
    """Care reprocess must not reuse an older failed PipelineRun."""
    client = _AdmissionClient()
    store = PipelineStageStore(client)
    shared_key = build_admission_key(_body("old-run"))
    client.runs_by_key[shared_key] = {
        "id": "old-run",
        "admission_key": shared_key,
        "first_step_enqueued": True,
        "status": "failed",
    }
    client.runs_by_id["old-run"] = client.runs_by_key[shared_key]
    viewer_body = {
        **_body("viewer-run-new"),
        "context": {
            "source": "patient-viewer",
            "referral_id": "ref-1",
            "document_reference_id": "dr-1",
        },
    }
    result = store.admit_run(
        StepRequest.from_message(viewer_body),
        admission_key=build_admission_key(viewer_body),
    )
    assert result.run_id == "viewer-run-new"
    assert client.runs_by_id["viewer-run-new"]["id"] == "viewer-run-new"
