from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

# Test envs may not have Azure SDK installed; stub required imports used by config.
azure_mod = types.ModuleType("azure")
azure_identity_mod = types.ModuleType("azure.identity")
azure_identity_aio_mod = types.ModuleType("azure.identity.aio")
azure_keyvault_mod = types.ModuleType("azure.keyvault")
azure_keyvault_secrets_mod = types.ModuleType("azure.keyvault.secrets")


class _DummyAzureClient:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)


azure_identity_mod.DefaultAzureCredential = _DummyAzureClient
azure_identity_aio_mod.DefaultAzureCredential = _DummyAzureClient
azure_keyvault_secrets_mod.SecretClient = _DummyAzureClient
sys.modules.setdefault("azure", azure_mod)
sys.modules.setdefault("azure.identity", azure_identity_mod)
sys.modules.setdefault("azure.identity.aio", azure_identity_aio_mod)
sys.modules.setdefault("azure.keyvault", azure_keyvault_mod)
sys.modules.setdefault("azure.keyvault.secrets", azure_keyvault_secrets_mod)

from app.routers.patients import (
    BatchResetAndRecodeRequest,
    BatchResetEncounterItem,
    batch_reset_and_recode_encounters,
)


class _FakeSession:
    def __init__(self, encounter_ids: set[str]):
        self._encounter_ids = encounter_ids

    def run(self, _query, **kwargs):
        encounter_id = kwargs.get("encounter_id")
        if encounter_id in self._encounter_ids:
            return [{"encounter_id": encounter_id, "text": "note"}]
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    def __init__(self, encounter_ids: set[str]):
        self._encounter_ids = encounter_ids

    def run(self, _query, **kwargs):
        _ = kwargs
        return []

    def session(self):
        return _FakeSession(self._encounter_ids)

    def close(self):
        return None


@pytest.mark.asyncio
async def test_batch_reset_and_recode_queues_all(monkeypatch):
    sent = []
    recorded = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.routers.patients.PatientGraphClient",
        lambda: _FakeClient({"enc-1", "enc-2"}),
    )
    monkeypatch.setattr(
        "app.routers.patients.require_patient_in_scope",
        lambda client, scope, patient_id: None,
    )
    monkeypatch.setattr(
        "app.routers.patients.reset_encounter",
        lambda patient_id, encounter_id, session: {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "links_deleted": 1,
        },
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )
    monkeypatch.setattr(
        "app.routers.patients._record_case_finding_selection",
        lambda **kwargs: recorded.append(kwargs),
    )

    result = await batch_reset_and_recode_encounters(
        BatchResetAndRecodeRequest(
            items=[
                BatchResetEncounterItem(patient_id="p-1", encounter_id="enc-1"),
                BatchResetEncounterItem(patient_id="p-1", encounter_id="enc-2"),
            ],
            trigger_analysis=False,
            dry_run=False,
            search_context={
                "query_audit_id": "audit-1",
                "original_query": "breast lump",
            },
        ),
        scope=None,  # type: ignore[arg-type]
    )

    assert result["requested"] == 2
    assert result["queued_count"] == 2
    assert result["failed_count"] == 0
    assert len(result["queued"]) == 2
    assert sent[0][1].body["plan_definition_id"] == "pd-gp-encounter-coding"
    assert sent[0][1].body["mode"] == "extract_encounter"
    assert sent[0][1].body["trigger_analysis"] is False
    assert len(recorded) == 2
    assert recorded[0]["search_context"]["query_audit_id"] == "audit-1"


@pytest.mark.asyncio
async def test_batch_reset_and_recode_reports_partial_failures(monkeypatch):
    sent = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

        async def close(self):
            return None

    monkeypatch.setattr(
        "app.routers.patients.PatientGraphClient",
        lambda: _FakeClient({"enc-1"}),
    )

    def _require_scope(_client, _scope, patient_id):
        if patient_id == "blocked":
            raise HTTPException(status_code=403, detail="forbidden")

    monkeypatch.setattr("app.routers.patients.require_patient_in_scope", _require_scope)
    monkeypatch.setattr(
        "app.routers.patients.reset_encounter",
        lambda patient_id, encounter_id, session: {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "links_deleted": 1,
        },
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    result = await batch_reset_and_recode_encounters(
        BatchResetAndRecodeRequest(
            items=[
                BatchResetEncounterItem(patient_id="p-1", encounter_id="enc-1"),
                BatchResetEncounterItem(patient_id="p-1", encounter_id="missing"),
                BatchResetEncounterItem(patient_id="blocked", encounter_id="enc-z"),
            ],
            trigger_analysis=True,
            dry_run=False,
        ),
        scope=None,  # type: ignore[arg-type]
    )

    assert result["queued_count"] == 1
    assert result["failed_count"] == 2
    assert result["trigger_analysis"] is True
    errors = {f["encounter_id"]: f["error"] for f in result["failed"]}
    assert "missing" in errors
    assert "enc-z" in errors
    assert sent[0][1].body["trigger_analysis"] is True
