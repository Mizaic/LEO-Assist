"""Handler for HCCP chunks-ready handoff messages.

Atlas trace:
  DI: DI-6B52E28E
  DO: DO-4B8D8AEB
  VT: VT-66810B48
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from libs.cypher.hccp_bridge_queries import (
    resolve_hccp_chunk_ref,
    update_hccp_data_request_status,
)
from libs.hccp.events import HCCPChunksReadyPayload

logger = logging.getLogger(__name__)


@dataclass
class HCCPBridgeResult:
    status: str
    resolved_count: int = 0
    missing_count: int = 0
    coded_chunks: int = 0
    documents_written: int = 0
    coding_error_count: int = 0
    error: str | None = None


class HCCPBridgeOrchestrator:
    """Validate HCCP chunk refs and update the HCCP DataRequest status."""

    def __init__(
        self,
        *,
        patient_graph_client: Any | None = None,
        chunk_coder: Any | None = None,
    ) -> None:
        self._client = patient_graph_client
        self._chunk_coder = chunk_coder

    async def run(self, body: dict[str, Any]) -> HCCPBridgeResult:
        try:
            payload = HCCPChunksReadyPayload.model_validate(body)
        except ValidationError as exc:
            return self._record_validation_error(body, exc)

        client = self._client_or_default()
        with client.session() as session:
            resolved: list[dict[str, Any]] = []
            missing: list[dict[str, Any]] = []
            for ref in payload.chunk_refs:
                row = resolve_hccp_chunk_ref(session, ref)
                if row is None:
                    missing.append(ref.model_dump())
                else:
                    resolved.append(row)

            coding = self._run_coding(session, payload, resolved)
            status = self._status_for_counts(
                len(resolved),
                len(missing),
                coding_error_count=len(coding["errors"]),
            )
            summary = self._summary(payload, resolved, missing, coding)
            update_hccp_data_request_status(
                session,
                data_request_id=payload.data_request_id,
                status=status,
                summary=summary,
                error=self._error_for_status(status, missing, coding["errors"]),
            )

        logger.info(
            "HCCP chunks-ready processed: data_request_id=%s status=%s",
            payload.data_request_id,
            status,
        )
        return HCCPBridgeResult(
            status=status,
            resolved_count=len(resolved),
            missing_count=len(missing),
            coded_chunks=coding["coded_chunks"],
            documents_written=coding["documents_written"],
            coding_error_count=len(coding["errors"]),
        )

    def _record_validation_error(
        self, body: dict[str, Any], exc: ValidationError
    ) -> HCCPBridgeResult:
        data_request_id = str(body.get("data_request_id") or "").strip()
        message = str(exc)
        if data_request_id:
            client = self._client_or_default()
            with client.session() as session:
                update_hccp_data_request_status(
                    session,
                    data_request_id=data_request_id,
                    status="error",
                    summary={
                        "handler": "hccp_chunks_ready",
                        "error": "payload_validation_failed",
                    },
                    error=message,
                )
        logger.warning("Invalid HCCP chunks-ready payload: %s", message)
        return HCCPBridgeResult(status="error", error=message)

    @staticmethod
    def _status_for_counts(
        resolved_count: int, missing_count: int, *, coding_error_count: int = 0
    ) -> str:
        if missing_count == 0 and coding_error_count == 0:
            return "success"
        if resolved_count > 0:
            return "partial_success"
        return "error"

    @staticmethod
    def _summary(
        payload: HCCPChunksReadyPayload,
        resolved: list[dict[str, Any]],
        missing: list[dict[str, Any]],
        coding: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "handler": "hccp_chunks_ready",
            "run_id": payload.run_id,
            "patient_id": payload.patient_id,
            "referral_request_id": payload.referral_request_id,
            "resolved_count": len(resolved),
            "missing_count": len(missing),
            "resolved_chunk_ids": [row.get("chunk_id") for row in resolved],
            "missing_refs": missing,
            "outputs": payload.outputs.model_dump(),
            "coded_chunks": coding["coded_chunks"],
            "documents_written": coding["documents_written"],
            "coding_error_count": len(coding["errors"]),
            "coding_errors": coding["errors"],
        }

    def _run_coding(
        self,
        session: Any,
        payload: HCCPChunksReadyPayload,
        resolved: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not payload.outputs.code:
            return {"coded_chunks": 0, "documents_written": 0, "errors": []}
        coder = self._chunk_coder_or_default()
        coded_chunks = 0
        documents_written = 0
        errors: list[dict[str, Any]] = []
        for row in resolved:
            try:
                result = coder.code_chunk(row, session=session, run_id=payload.run_id)
            except Exception as exc:
                logger.exception("HCCP chunk coding failed")
                errors.append({"chunk_id": row.get("chunk_id"), "error": str(exc)})
                continue
            coded_chunks += 1
            documents_written += int(result.documents_written or 0)
        return {
            "coded_chunks": coded_chunks,
            "documents_written": documents_written,
            "errors": errors,
        }

    def _chunk_coder_or_default(self) -> Any:
        if self._chunk_coder is not None:
            return self._chunk_coder
        from services.pipeline_worker.app.services.hccp_chunk_coder import HCCPChunkCoder

        return HCCPChunkCoder()

    @staticmethod
    def _error_for_status(
        status: str, missing: list[dict[str, Any]], coding_errors: list[dict[str, Any]]
    ) -> str | None:
        if status == "success":
            return None
        if missing and coding_errors:
            return "One or more chunks were not found or failed coding"
        if coding_errors:
            return "One or more chunks failed coding"
        return "One or more chunks were not found"

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()


async def handle_hccp_chunks_message(body: dict[str, Any]) -> HCCPBridgeResult:
    """Entry point used by pipeline_worker message dispatch."""
    return await HCCPBridgeOrchestrator().run(body)
