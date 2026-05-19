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
    error: str | None = None


class HCCPBridgeOrchestrator:
    """Validate HCCP chunk refs and update the HCCP DataRequest status."""

    def __init__(self, *, patient_graph_client: Any | None = None) -> None:
        self._client = patient_graph_client

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

            status = self._status_for_counts(len(resolved), len(missing))
            summary = self._summary(payload, resolved, missing)
            update_hccp_data_request_status(
                session,
                data_request_id=payload.data_request_id,
                status=status,
                summary=summary,
                error=None if status == "success" else "One or more chunks were not found",
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
    def _status_for_counts(resolved_count: int, missing_count: int) -> str:
        if missing_count == 0:
            return "success"
        if resolved_count > 0:
            return "partial_success"
        return "error"

    @staticmethod
    def _summary(
        payload: HCCPChunksReadyPayload,
        resolved: list[dict[str, Any]],
        missing: list[dict[str, Any]],
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
        }

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()


async def handle_hccp_chunks_message(body: dict[str, Any]) -> HCCPBridgeResult:
    """Entry point used by pipeline_worker message dispatch."""
    return await HCCPBridgeOrchestrator().run(body)
