"""
Fire-and-forget FHIR R4B AuditEvent emitter.

Emits structured JSON to stdout (captured by ACA Log Analytics) AND
sends a POST to the FHIR API /fhir/AuditEvent endpoint in a background
thread so audit never blocks the request path.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_FHIR_API_URL = ""


def _fhir_url() -> str:
    global _FHIR_API_URL
    if not _FHIR_API_URL:
        _FHIR_API_URL = os.environ.get("FHIR_API_URL", "http://fhir-api")
    return _FHIR_API_URL


def _build_event(
    *,
    type_code: str,
    type_display: str,
    outcome: str,
    agent_email: str | None,
    agent_role: str | None,
    source_service: str,
    entity_id: str | None = None,
    entity_type: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    event: dict[str, Any] = {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": type_code,
            "display": type_display,
        },
        "recorded": now,
        "outcome": outcome,
        "agent": [{"who": {"display": agent_email or "system"}, "requestor": True}],
        "source": {"site": source_service, "observer": {"display": source_service}},
    }
    if agent_role:
        event["agent"][0]["role"] = [{"text": agent_role}]
    if entity_id:
        event["entity"] = [
            {
                "what": {"identifier": {"value": entity_id}},
                "type": {"display": entity_type or ""},
            }
        ]
    return event


def _emit_async(event: dict[str, Any]) -> None:
    logger.info("audit_event %s", event, extra={"audit": True})

    auth_secret = os.environ.get("SERVICE_AUTH_SECRET", "")
    headers = {}
    if auth_secret:
        headers["Authorization"] = f"Bearer {auth_secret}"

    def _post() -> None:
        try:
            httpx.post(
                f"{_fhir_url()}/fhir/AuditEvent",
                json=event,
                headers=headers,
                timeout=5,
            )
        except Exception as exc:
            logger.debug("AuditEvent POST failed (non-fatal): %s", exc)

    threading.Thread(target=_post, daemon=True).start()


def emit_auth_event(
    *,
    outcome: str,
    agent_email: str | None = None,
    description: str = "",
    source_service: str = "core-api",
) -> None:
    _emit_async(
        _build_event(
            type_code="110114",
            type_display="User Authentication",
            outcome=outcome,
            agent_email=agent_email,
            agent_role=None,
            source_service=source_service,
            description=description,
        )
    )


def emit_access_event(
    *,
    outcome: str,
    agent_email: str | None = None,
    agent_role: str | None = None,
    entity_id: str | None = None,
    entity_type: str | None = None,
    source_service: str = "core-api",
) -> None:
    _emit_async(
        _build_event(
            type_code="110110",
            type_display="Patient Record",
            outcome=outcome,
            agent_email=agent_email,
            agent_role=agent_role,
            source_service=source_service,
            entity_id=entity_id,
            entity_type=entity_type,
        )
    )


def emit_model_event(
    *,
    outcome: str,
    action: str,
    agent_email: str | None = None,
    model_version: str | None = None,
    source_service: str = "core-api",
) -> None:
    _emit_async(
        _build_event(
            type_code="110153",
            type_display="Application Activity",
            outcome=outcome,
            agent_email=agent_email,
            agent_role="admin",
            source_service=source_service,
            entity_id=model_version,
            entity_type="model-version",
            description=action,
        )
    )


def emit_pipeline_event(
    *,
    outcome: str,
    patient_id: str,
    agent_email: str | None = None,
    source_service: str = "core-api",
) -> None:
    _emit_async(
        _build_event(
            type_code="110112",
            type_display="Query",
            outcome=outcome,
            agent_email=agent_email,
            agent_role=None,
            source_service=source_service,
            entity_id=patient_id,
            entity_type="patient",
        )
    )


def emit_application_event(
    *,
    outcome: str,
    agent_email: str | None = None,
    description: str = "",
    source_service: str = "core-api",
    entity_id: str | None = None,
    entity_type: str | None = None,
) -> None:
    """General-purpose application activity audit event."""
    _emit_async(
        _build_event(
            type_code="110153",
            type_display="Application Activity",
            outcome=outcome,
            agent_email=agent_email,
            agent_role=None,
            source_service=source_service,
            entity_id=entity_id,
            entity_type=entity_type,
            description=description,
        )
    )


def emit_ods_sync_summary(
    *,
    run_id: str,
    checked: int,
    mismatches: int,
    closures: int,
    errors: int,
    aborted: bool = False,
    source_service: str = "ods-sync",
) -> None:
    """Emit an ODS sync run summary as a FHIR AuditEvent."""
    outcome = "8" if aborted else "0"  # 8 = Serious Failure, 0 = Success
    description = (
        f"ODS sync {'ABORTED' if aborted else 'complete'}: "
        f"run_id={run_id} checked={checked} mismatches={mismatches} "
        f"closures={closures} errors={errors}"
    )
    _emit_async(
        _build_event(
            type_code="110153",
            type_display="Application Activity",
            outcome=outcome,
            agent_email=None,
            agent_role="system",
            source_service=source_service,
            entity_id=run_id,
            entity_type="ods-sync-run",
            description=description,
        )
    )


def emit_ods_closure_alert(
    *,
    org_id: str,
    org_name: str,
    ods_code: str,
    run_id: str,
    source_service: str = "ods-sync",
) -> None:
    """Emit a closure alert AuditEvent when ODS reports an org as Inactive or not found."""
    description = f"ODS closure alert: org_id={org_id} name={org_name} ods_code={ods_code} run_id={run_id}"
    _emit_async(
        _build_event(
            type_code="110110",
            type_display="Patient Record",
            outcome="4",  # Minor failure — informational alert requiring human review
            agent_email=None,
            agent_role="system",
            source_service=source_service,
            entity_id=org_id,
            entity_type="organisation",
            description=description,
        )
    )
