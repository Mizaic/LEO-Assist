"""Queue contract for HCCP chunks-ready handoff messages.

Atlas trace:
  DI: DI-6B52E28E
  DO: DO-4B8D8AEB
  VT: VT-66810B48
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HCCPChunkRef(BaseModel):
    """Reference to one HCCP-created chunk under a DocumentReference."""

    document_reference_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    chunk_idx: int | None = None
    category_key: str | None = None
    classification_confidence: float | None = None


class HCCPRequestedOutputs(BaseModel):
    """Downstream work flags retained for later implementation phases."""

    code: bool = True
    evaluate_abnormal_tests: bool = True
    generate_sbar: bool = True


class HCCPChunksReadyPayload(BaseModel):
    """Validated body for event_type='hccp_chunks_ready'."""

    message_type: Literal["hccp_core_ai_chunks_ready"] = "hccp_core_ai_chunks_ready"
    event_type: Literal["hccp_chunks_ready"]
    run_id: str = Field(..., min_length=1)
    data_request_id: str = Field(..., min_length=1)
    patient_id: str = Field(..., min_length=1)
    referral_request_id: str | None = None
    organization_id: str | None = None
    service_id: str | None = None
    chunk_refs: list[HCCPChunkRef] = Field(..., min_length=1)
    outputs: HCCPRequestedOutputs = Field(default_factory=HCCPRequestedOutputs)

    @field_validator("chunk_refs")
    @classmethod
    def _require_chunk_refs(
        cls, value: list[HCCPChunkRef]
    ) -> list[HCCPChunkRef]:
        if not value:
            raise ValueError("chunk_refs must contain at least one item")
        return value
