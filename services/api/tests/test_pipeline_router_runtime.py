from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.pipeline import (
    RunPatientRequest,
    list_pipeline_subgraphs,
    run_patient,
    run_pipeline,
)


def test_subgraphs_endpoint_exposes_runtime_only_capabilities():
    payload = list_pipeline_subgraphs(scope=None)  # type: ignore[arg-type]
    ids = {item["id"] for item in payload["subgraphs"]}
    assert "surface_form_validation" in ids
    assert "guidance_rule_extraction" in ids
    assert "queue_publish" in ids


def test_legacy_run_endpoint_is_explicitly_retired():
    with pytest.raises(HTTPException) as exc:
        run_pipeline(
            payload=type(
                "Payload",
                (),
                {
                    "patient_ids": ["p-1"],
                    "cohort_id": None,
                    "org_id": None,
                    "max_encounters_per_patient": None,
                    "dry_run": False,
                },
            )(),
            scope=None,  # type: ignore[arg-type]
            service=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_run_patient_queues_pipeline_jobs(monkeypatch):
    sent = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.routers.pipeline._require_patients_in_scope",
        lambda scope, patient_ids: None,
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    result = await run_patient(
        RunPatientRequest(patient_id="p-1", action="code_new", preview=False),
        scope=None,  # type: ignore[arg-type]
    )

    assert result["queued"] == 1
    assert sent[0][0] == "pipeline-jobs"
    assert sent[0][1].body["event_type"] == "encounter-created"
