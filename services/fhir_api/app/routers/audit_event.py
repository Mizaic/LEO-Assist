"""FHIR R4B AuditEvent ingestion endpoint (GAP-012).

Accepts POST /fhir/AuditEvent from other internal services (core-api, coding-worker,
etc.) via the audit_emitter lib. Validates the shared-secret token and writes a
structured log entry to stdout (captured by ACA Log Analytics) and persists to Neo4j.

The Neo4j write is best-effort and non-blocking; a log failure never interrupts the
calling service.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from libs.auth.service_auth import verify_service_token

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditEventBody(BaseModel):
    class Config:
        extra = "allow"  # accept full FHIR R4B AuditEvent without strict schema

    resourceType: str = "AuditEvent"
    recorded: str = ""
    outcome: str = ""


@router.post("/AuditEvent", status_code=202)
def create_audit_event(
    body: dict[str, Any],
    request: Request,
    _: None = Depends(verify_service_token),
) -> dict[str, str]:
    """Receive, log, and persist a FHIR R4B AuditEvent from an internal service."""
    resource_type = body.get("resourceType", "")
    if resource_type != "AuditEvent":
        logger.warning("AuditEvent endpoint received unexpected resourceType: %s", resource_type)

    logger.info(
        "fhir_audit_event outcome=%s recorded=%s agent=%s",
        body.get("outcome"),
        body.get("recorded"),
        _extract_agent(body),
        extra={"audit": True, "fhir_audit": body},
    )

    _persist_to_neo4j(body)

    return {"accepted": "true"}


def _extract_agent(body: dict[str, Any]) -> str:
    agents = body.get("agent", [])
    if agents:
        who = agents[0].get("who", {})
        return who.get("display") or who.get("identifier", {}).get("value") or "unknown"
    return "unknown"


def _persist_to_neo4j(body: dict[str, Any]) -> None:
    try:
        from libs.neo4j_client.client import PatientGraphClient
        client = PatientGraphClient()
        client.run(
            """
            CREATE (a:AuditEvent {
                recorded: $recorded,
                outcome: $outcome,
                type_code: $type_code,
                agent: $agent,
                source: $source,
                entity_id: $entity_id
            })
            """,
            recorded=body.get("recorded", ""),
            outcome=body.get("outcome", ""),
            type_code=(body.get("type") or {}).get("code", ""),
            agent=_extract_agent(body),
            source=(body.get("source") or {}).get("site", ""),
            entity_id=_extract_entity_id(body),
        )
        client.close()
    except Exception as exc:
        logger.debug("AuditEvent Neo4j persist failed (non-fatal): %s", exc)


def _extract_entity_id(body: dict[str, Any]) -> str:
    entities = body.get("entity", [])
    if entities:
        what = entities[0].get("what", {})
        return what.get("identifier", {}).get("value") or ""
    return ""
