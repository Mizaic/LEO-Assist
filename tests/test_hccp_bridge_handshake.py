from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "services" / "pipeline_worker" / "app" / "main.py"


def _valid_payload() -> dict[str, Any]:
    return {
        "message_type": "hccp_core_ai_chunks_ready",
        "event_type": "hccp_chunks_ready",
        "run_id": "run-1",
        "data_request_id": "dr-1",
        "patient_id": "patient-1",
        "referral_request_id": "ref-1",
        "organization_id": "org-1",
        "service_id": "svc-1",
        "chunk_refs": [
            {
                "document_reference_id": "doc-1",
                "chunk_id": "0",
                "chunk_idx": 0,
                "category_key": "investigations",
            }
        ],
        "outputs": {
            "code": True,
            "evaluate_abnormal_tests": True,
            "generate_sbar": True,
        },
    }


def test_hccp_chunks_payload_accepts_valid_contract() -> None:
    from libs.hccp.events import HCCPChunksReadyPayload

    payload = HCCPChunksReadyPayload.model_validate(_valid_payload())

    assert payload.event_type == "hccp_chunks_ready"
    assert payload.data_request_id == "dr-1"
    assert payload.chunk_refs[0].document_reference_id == "doc-1"
    assert payload.chunk_refs[0].chunk_id == "0"
    assert payload.chunk_refs[0].chunk_idx == 0
    assert payload.outputs.generate_sbar is True


def test_hccp_chunks_payload_rejects_missing_data_request_id() -> None:
    from libs.hccp.events import HCCPChunksReadyPayload

    body = _valid_payload()
    body.pop("data_request_id")

    with pytest.raises(ValidationError):
        HCCPChunksReadyPayload.model_validate(body)


def test_hccp_chunks_payload_rejects_empty_chunk_refs() -> None:
    from libs.hccp.events import HCCPChunksReadyPayload

    body = _valid_payload()
    body["chunk_refs"] = []

    with pytest.raises(ValidationError):
        HCCPChunksReadyPayload.model_validate(body)


class _SingleResult:
    def __init__(self, row: dict[str, Any] | None):
        self._row = row

    def single(self) -> dict[str, Any] | None:
        return self._row


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any] | None]):
        self.rows = list(rows)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **kwargs: Any) -> _SingleResult:
        self.calls.append((query, dict(kwargs)))
        row = self.rows.pop(0) if self.rows else None
        return _SingleResult(row)


class _FakeClient:
    def __init__(self, session: _FakeSession):
        self._session = session

    def session(self) -> "_FakeClient":
        return self

    def __enter__(self) -> _FakeSession:
        return self._session

    def __exit__(self, *_args: Any) -> bool:
        return False


def test_resolve_hccp_chunk_ref_matches_core_id_or_hccp_index() -> None:
    from libs.cypher.hccp_bridge_queries import (
        RESOLVE_HCCP_CHUNK_REF,
        resolve_hccp_chunk_ref,
    )
    from libs.hccp.events import HCCPChunkRef

    session = _FakeSession(
        [
            {
                "chunk_id": "core-chunk-1",
                "document_reference_id": "doc-1",
                "chunk_idx": 0,
                "text": "Hb 85 g/L",
                "category_key": "investigations",
            }
        ]
    )

    resolved = resolve_hccp_chunk_ref(
        session,
        HCCPChunkRef(
            document_reference_id="doc-1",
            chunk_id="0",
            chunk_idx=0,
            category_key="investigations",
        ),
    )

    assert resolved is not None
    assert resolved["chunk_id"] == "core-chunk-1"
    query, params = session.calls[0]
    assert query == RESOLVE_HCCP_CHUNK_REF
    assert params["document_reference_id"] == "doc-1"
    assert params["chunk_id"] == "0"
    assert params["chunk_idx"] == 0


def test_update_hccp_data_request_status_writes_summary_json() -> None:
    from libs.cypher.hccp_bridge_queries import (
        UPDATE_HCCP_DATA_REQUEST_STATUS,
        update_hccp_data_request_status,
    )

    session = _FakeSession([{"status": "success"}])

    update_hccp_data_request_status(
        session,
        data_request_id="dr-1",
        status="success",
        summary={"resolved_count": 1, "missing_count": 0},
        error=None,
    )

    query, params = session.calls[0]
    assert query == UPDATE_HCCP_DATA_REQUEST_STATUS
    assert params["data_request_id"] == "dr-1"
    assert params["status"] == "success"
    assert '"resolved_count": 1' in params["summary_json"]
    assert params["error"] is None


@pytest.mark.asyncio
async def test_hccp_orchestrator_marks_success_when_all_chunks_resolve() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            {"status": "success"},
        ]
    )
    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session)
    ).run(_valid_payload())

    assert result.status == "success"
    assert result.resolved_count == 1
    assert result.missing_count == 0
    assert session.calls[-1][1]["status"] == "success"


@pytest.mark.asyncio
async def test_hccp_orchestrator_marks_partial_success_for_missing_chunks() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    body = _valid_payload()
    body["chunk_refs"].append(
        {
            "document_reference_id": "doc-1",
            "chunk_id": "missing",
            "category_key": "clinical_history",
        }
    )
    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            None,
            {"status": "partial_success"},
        ]
    )

    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session)
    ).run(body)

    assert result.status == "partial_success"
    assert result.resolved_count == 1
    assert result.missing_count == 1
    assert session.calls[-1][1]["status"] == "partial_success"


@pytest.mark.asyncio
async def test_hccp_orchestrator_records_error_for_invalid_payload() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    body = _valid_payload()
    body["chunk_refs"] = []
    session = _FakeSession([{"status": "error"}])

    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session)
    ).run(body)

    assert result.status == "error"
    assert result.error
    assert session.calls[-1][1]["data_request_id"] == "dr-1"
    assert session.calls[-1][1]["status"] == "error"


def test_pipeline_worker_dispatches_hccp_chunks_before_workflow_engine() -> None:
    text = MAIN_PATH.read_text(encoding="utf-8")

    assert "handle_hccp_chunks_message" in text
    assert 'body.get("event_type") == "hccp_chunks_ready"' in text
    assert text.index("hccp_chunks_ready") < text.index("handler.handle_message")
