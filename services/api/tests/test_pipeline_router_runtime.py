from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.pipeline import (
    PIPELINE_QUEUE,
    RunAllPatientsRequest,
    RunCohortRequest,
    RunPatientRequest,
    get_progress_status,
    list_pipeline_subgraphs,
    run_all_patients,
    run_patient,
    run_cohort,
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


def test_progress_status_maps_cached_terminal_event(monkeypatch):
    class _RedisClient:
        def get(self, key):
            _ = key
            return b'{"type":"run_completed","status":"completed"}'

    class _RedisModule:
        @staticmethod
        def from_url(url):
            _ = url
            return _RedisClient()

    import sys

    monkeypatch.setitem(sys.modules, "redis", _RedisModule())
    payload = get_progress_status("run-123")
    assert payload["run_id"] == "run-123"
    assert payload["state"] == "completed"


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
        "app.routers.pipeline._expand_patients_to_clinical_encounters",
        lambda patient_ids: [
            {
                "patient_id": patient_ids[0],
                "encounter_id": "enc-1",
                "encounter_text": "Patient has cough.",
            }
        ],
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
    assert sent[0][0] == PIPELINE_QUEUE
    assert sent[0][1].body["event_type"] == "encounter-created"
    assert sent[0][1].body["encounter_id"] == "enc-1"
    assert sent[0][1].body["context"]["trigger_analysis"] is False
    assert result["stream_path"].startswith("/api/pipeline/progress/")


@pytest.mark.asyncio
async def test_run_patient_full_pipeline_enables_analysis_trigger(monkeypatch):
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
        "app.routers.pipeline._expand_patients_to_clinical_encounters",
        lambda patient_ids: [
            {
                "patient_id": patient_ids[0],
                "encounter_id": "enc-2",
                "encounter_text": "Patient has fatigue.",
            }
        ],
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    result = await run_patient(
        RunPatientRequest(patient_id="p-2", action="full_pipeline", preview=False),
        scope=None,  # type: ignore[arg-type]
    )

    assert result["queued"] == 1
    assert sent[0][1].body["context"]["trigger_analysis"] is True


@pytest.mark.asyncio
async def test_run_cohort_partial_publish_is_failed(monkeypatch):
    class _Bus:
        def __init__(self):
            self.count = 0

        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            _ = (queue_or_topic, message, schedule_after_seconds)
            self.count += 1
            if self.count == 2:
                raise RuntimeError("simulated bus failure")

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.routers.pipeline._require_patients_in_scope",
        lambda scope, patient_ids: None,
    )
    monkeypatch.setattr(
        "app.routers.pipeline._expand_patients_to_clinical_encounters",
        lambda patient_ids: [
            {
                "patient_id": pid,
                "encounter_id": f"enc-{i}",
                "encounter_text": "Clinical note",
            }
            for i, pid in enumerate(patient_ids, start=1)
        ],
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    with pytest.raises(HTTPException) as exc:
        await run_cohort(
            RunCohortRequest(
                patient_ids=["p-1", "p-2", "p-3"],
                action="full_pipeline",
                preview=False,
            ),
            scope=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_run_all_patients_preview_returns_counts(monkeypatch):
    monkeypatch.setattr(
        "app.routers.pipeline._resolve_scope_patients",
        lambda scope, org_id: ["p-1", "p-2"],
    )
    monkeypatch.setattr(
        "app.routers.pipeline._expand_patients_to_clinical_encounters",
        lambda patient_ids: [
            {"patient_id": "p-1", "encounter_id": "enc-1"},
            {"patient_id": "p-2", "encounter_id": "enc-2"},
            {"patient_id": "p-2", "encounter_id": "enc-3"},
        ],
    )

    result = await run_all_patients(
        RunAllPatientsRequest(org_id="org-1", preview=True),
        scope=None,  # type: ignore[arg-type]
    )
    assert result["preview"] is True
    assert result["patient_count"] == 2
    assert result["encounter_count"] == 3
    assert "confirmation_text_required" in result


@pytest.mark.asyncio
async def test_run_all_patients_requires_confirmation_and_queues(monkeypatch):
    sent = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.routers.pipeline._resolve_scope_patients",
        lambda scope, org_id: ["p-1", "p-2"],
    )
    monkeypatch.setattr(
        "app.routers.pipeline._expand_patients_to_clinical_encounters",
        lambda patient_ids: [
            {"patient_id": "p-1", "encounter_id": "enc-1"},
            {"patient_id": "p-2", "encounter_id": "enc-2"},
        ],
    )
    monkeypatch.setattr(
        "app.routers.pipeline._clean_patients",
        lambda patient_ids: {"documents": 4, "episodes": 2},
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    with pytest.raises(HTTPException) as exc:
        await run_all_patients(
            RunAllPatientsRequest(org_id="org-1", preview=False),
            scope=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400

    result = await run_all_patients(
        RunAllPatientsRequest(
            org_id="org-1",
            preview=False,
            acknowledge_expensive=True,
            acknowledge_destructive=True,
            acknowledge_background=True,
            confirmation_text="RESET AND REPROCESS ALL PATIENTS",
            expected_patient_count=2,
        ),
        scope=None,  # type: ignore[arg-type]
    )
    assert result["preview"] is False
    assert result["patient_count"] == 2
    assert result["encounter_count"] == 2
    assert result["queued"] == 2
    assert result["stream_path"].startswith("/api/pipeline/progress/")
    assert sent[0][0] == PIPELINE_QUEUE
