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


def test_hccp_chunks_payload_defaults_to_handshake_only() -> None:
    from libs.hccp.events import HCCPChunksReadyPayload

    body = _valid_payload()
    body.pop("outputs")

    payload = HCCPChunksReadyPayload.model_validate(body)

    assert payload.outputs.code is False
    assert payload.outputs.evaluate_abnormal_tests is False
    assert payload.outputs.generate_sbar is False


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


def test_resolve_hccp_chunk_ref_assigns_bridge_stable_chunk_id() -> None:
    from libs.cypher.hccp_bridge_queries import RESOLVE_HCCP_CHUNK_REF

    assert "SET c.id = coalesce(" in RESOLVE_HCCP_CHUNK_REF
    assert "dr.id + ':chunk:'" in RESOLVE_HCCP_CHUNK_REF
    assert "RETURN c.id AS chunk_id" in RESOLVE_HCCP_CHUNK_REF


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

    body = _valid_payload()
    body["outputs"]["code"] = False
    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            {"status": "success"},
        ]
    )
    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session)
    ).run(body)

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
    body["outputs"]["code"] = False
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


class _FakeGraph:
    def __init__(self, result: dict[str, Any]):
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(state))
        return dict(self.result)


def test_chunk_coder_runs_subgraphs_and_writes_chunk_documents() -> None:
    from services.pipeline_worker.app.services.hccp_chunk_coder import HCCPChunkCoder

    writes: list[dict[str, Any]] = []

    def _writer(source_id: str, payload, session, **kwargs):
        writes.append(
            {
                "source_id": source_id,
                "payload": payload,
                "kwargs": kwargs,
            }
        )
        return 1

    extraction = _FakeGraph(
        {
            "sentences": [{"sentence_id": "s1", "text": "Hb 85 g/L"}],
            "entities": [
                {
                    "text": "Hb",
                    "label": "observable_entity",
                    "semantic_tag": "observable entity",
                    "__sentence_id": "s1",
                    "value": 85,
                    "unit": "g/L",
                }
            ],
        }
    )
    post_processing = _FakeGraph(
        {
            "entities": [
                {
                    "text": "Hb",
                    "label": "observable_entity",
                    "semantic_tag": "observable entity",
                    "__sentence_id": "s1",
                    "value": 85,
                    "unit": "g/L",
                }
            ]
        }
    )
    terminology = _FakeGraph(
        {
            "entities": [
                {
                    "text": "Hb",
                    "label": "observable_entity",
                    "semantic_tag": "observable entity",
                    "__sentence_id": "s1",
                    "value": 85,
                    "unit": "g/L",
                    "concept_id": "1022431000000105",
                    "term": "Haemoglobin level",
                    "score": 0.93,
                }
            ]
        }
    )

    result = HCCPChunkCoder(
        extraction_graph=extraction,
        post_processing_graph=post_processing,
        terminology_graph=terminology,
        documents_writer=_writer,
    ).code_chunk(
        {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
        session=object(),
        run_id="run-1",
    )

    assert result.documents_written == 1
    assert result.entities_count == 1
    assert writes[0]["source_id"] == "chunk-1"
    assert writes[0]["kwargs"]["source_label"] == "Chunk"
    assert writes[0]["kwargs"]["source"] == "hccp_bridge"
    assert writes[0]["kwargs"]["run_id"] == "run-1"
    assert writes[0]["payload"][0]["terms"][0]["coding"]["snomed_concept_id"]


def test_chunk_coder_raises_when_subgraph_reports_errors() -> None:
    from services.pipeline_worker.app.services.hccp_chunk_coder import HCCPChunkCoder

    extraction = _FakeGraph(
        {
            "sentences": [],
            "entities": [],
            "errors": ["extraction failed"],
        }
    )

    with pytest.raises(RuntimeError, match="extraction failed"):
        HCCPChunkCoder(
            extraction_graph=extraction,
            post_processing_graph=_FakeGraph({"entities": []}),
            terminology_graph=_FakeGraph({"entities": []}),
            documents_writer=lambda *_args, **_kwargs: 0,
        ).code_chunk(
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            session=object(),
            run_id="run-1",
        )


class _FakeCoder:
    def __init__(self, documents_written: int = 1, fail: bool = False):
        self.documents_written = documents_written
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def code_chunk(self, chunk: dict[str, Any], *, session: Any, run_id: str):
        from services.pipeline_worker.app.services.hccp_chunk_coder import (
            HCCPChunkCodingResult,
        )

        self.calls.append({"chunk": chunk, "run_id": run_id})
        if self.fail:
            raise RuntimeError("coding failed")
        return HCCPChunkCodingResult(
            chunk_id=chunk["chunk_id"],
            documents_written=self.documents_written,
            entities_count=2,
        )


@pytest.mark.asyncio
async def test_hccp_orchestrator_invokes_coder_when_code_requested() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            {"status": "success"},
        ]
    )
    coder = _FakeCoder(documents_written=3)

    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session),
        chunk_coder=coder,
    ).run(_valid_payload())

    assert result.status == "success"
    assert len(coder.calls) == 1
    summary_json = session.calls[-1][1]["summary_json"]
    assert '"coded_chunks": 1' in summary_json
    assert '"documents_written": 3' in summary_json


@pytest.mark.asyncio
async def test_hccp_orchestrator_skips_coder_when_code_not_requested() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    body = _valid_payload()
    body["outputs"]["code"] = False
    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            {"status": "success"},
        ]
    )
    coder = _FakeCoder(documents_written=3)

    await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session),
        chunk_coder=coder,
    ).run(body)

    assert coder.calls == []
    summary_json = session.calls[-1][1]["summary_json"]
    assert '"coded_chunks": 0' in summary_json
    assert '"documents_written": 0' in summary_json


@pytest.mark.asyncio
async def test_hccp_orchestrator_reports_coding_errors() -> None:
    from services.pipeline_worker.app.services.hccp_bridge_orchestrator import (
        HCCPBridgeOrchestrator,
    )

    session = _FakeSession(
        [
            {"chunk_id": "chunk-1", "text": "Hb 85 g/L"},
            {"status": "partial_success"},
        ]
    )

    result = await HCCPBridgeOrchestrator(
        patient_graph_client=_FakeClient(session),
        chunk_coder=_FakeCoder(fail=True),
    ).run(_valid_payload())

    assert result.status == "partial_success"
    summary_json = session.calls[-1][1]["summary_json"]
    assert '"coding_error_count": 1' in summary_json
    assert "coding failed" in summary_json
