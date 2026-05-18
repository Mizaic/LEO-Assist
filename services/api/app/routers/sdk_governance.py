"""LEO widget host governance endpoints.

Atlas trace:
  DO: DO-5A298ABC
  DI: DI-2FBDAC7D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5A298ABC")

Operations endpoints used by LEO QMS / Clinical Safety Committee:

POST /sdk/governance/hosts
    Register a new embedding host.

POST /sdk/governance/hosts/{host_id}/artefacts
    Record evidence of one of the four mandatory artefacts.

POST /sdk/governance/hosts/{host_id}/ifu
    Record an IFU acknowledgement (with version).

GET  /sdk/governance/register
    Full register (for the quarterly Clinical Safety Committee
    review).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import host_governance

router = APIRouter(prefix="/sdk/governance", tags=["sdk-governance"])


class HostRegistration(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    contact: str = Field(..., min_length=1, max_length=256)


class ArtefactEvidence(BaseModel):
    artefact: Literal[
        "saas_embedding_agreement",
        "dpa",
        "dcb0129_reference",
        "ifu_acknowledged",
    ]
    evidence_uri: str = Field(..., min_length=1, max_length=2048)


class IfuAcknowledgement(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)


@router.post("/hosts")
def create_host(payload: HostRegistration) -> dict:
    record = host_governance.register_host(
        host_id=payload.host_id, name=payload.name, contact=payload.contact
    )
    return record.to_dict()


@router.post("/hosts/{host_id}/artefacts")
def record_artefact(host_id: str, payload: ArtefactEvidence) -> dict:
    try:
        record = host_governance.mark_artefact_received(
            host_id=host_id,
            artefact=payload.artefact,
            evidence_uri=payload.evidence_uri,
        )
    except host_governance.HostNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="host_not_registered",
        ) from exc
    return record.to_dict()


@router.post("/hosts/{host_id}/ifu")
def acknowledge_ifu(host_id: str, payload: IfuAcknowledgement) -> dict:
    try:
        record = host_governance.acknowledge_ifu(
            host_id=host_id, version=payload.version
        )
    except host_governance.HostNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="host_not_registered",
        ) from exc
    return record.to_dict()


@router.get("/register")
def get_register() -> list[dict]:
    return host_governance.list_hosts()
