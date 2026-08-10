"""Enqueue referral pipeline runs for selected document chunks.

Uses the same referral-received bus message as Validation Lab and
production referrals, with real tenant scope validation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from libs.patient_document_runs.queries import (
    ENSURE_REFERRAL_ASSESSMENT_ENCOUNTER,
    RESOLVE_DOCUMENT_RUN_CONTEXT,
)
from libs.referral_simulator.message import build_referral_received_message
from libs.sbar.trigger_chunk_scope import (
    TriggerChunkScopeRequest,
    validate_trigger_chunk_scope,
)
from libs.validation_lab.pipeline import (
    bootstrap_durable_lab_run,
    default_publish,
    list_stage_progress,
    poll_run_status,
)

logger = logging.getLogger(__name__)

DEFAULT_PLAN_ID = "pd-referral-assessment"
DEFAULT_PHASE_IDS = [
    "extraction",
    "verification",
    "persist",
    "guidance",
    "sbar",
]

PublishFn = Callable[[dict[str, Any], str], None]


@dataclass(frozen=True)
class DocumentRunContext:
    patient_id: str
    tenant_id: str
    document_reference_id: str
    referral_id: str
    encounter_id: str


@dataclass(frozen=True)
class StartDocumentRunResult:
    run_id: str
    status: str
    assessment_id: str
    error_message: str
    stage_progress: list[dict[str, str]]


class DocumentRunError(Exception):
    """Raised when a document run cannot be started or validated."""


def resolve_document_run_context(
    client: Any,
    *,
    patient_id: str,
    document_reference_id: str,
    tenant_fallback: str | None = None,
) -> DocumentRunContext:
    rows = client.run(
        RESOLVE_DOCUMENT_RUN_CONTEXT,
        patient_id=patient_id,
        document_reference_id=document_reference_id,
    )
    if not rows:
        raise DocumentRunError(
            "Document is not linked to this patient or could not be found."
        )
    row = rows[0]
    referral_id = str(row.get("referral_id") or "").strip()
    if not referral_id:
        raise DocumentRunError(
            "This document is not linked to a referral. "
            "Only referral documents can be reprocessed."
        )
    tenant_id = str(row.get("tenant_id") or "").strip()
    if not tenant_id and tenant_fallback:
        tenant_id = str(tenant_fallback).strip()
    if not tenant_id:
        raise DocumentRunError(
            "Patient tenant id is missing. Cannot validate chunk scope."
        )
    encounter_id = str(row.get("encounter_id") or "").strip()
    if not encounter_id:
        raise DocumentRunError("Referral encounter id could not be resolved.")
    client.run(
        ENSURE_REFERRAL_ASSESSMENT_ENCOUNTER,
        patient_id=patient_id,
        referral_id=referral_id,
        encounter_id=encounter_id,
    )
    return DocumentRunContext(
        patient_id=str(row.get("patient_id") or patient_id),
        tenant_id=tenant_id,
        document_reference_id=str(row.get("document_reference_id") or document_reference_id),
        referral_id=referral_id,
        encounter_id=encounter_id,
    )


def start_document_run(
    client: Any,
    *,
    patient_id: str,
    document_reference_id: str,
    chunk_ids: list[str],
    plan_id: str = DEFAULT_PLAN_ID,
    requested_by: str | None = None,
    publish: PublishFn | None = None,
    eager_durable_bootstrap: bool = True,
    tenant_fallback: str | None = None,
) -> StartDocumentRunResult:
    if not chunk_ids:
        raise DocumentRunError("Select at least one chunk to run the pipeline.")

    ctx = resolve_document_run_context(
        client,
        patient_id=patient_id,
        document_reference_id=document_reference_id,
        tenant_fallback=tenant_fallback,
    )
    with client.session() as session:
        scope = validate_trigger_chunk_scope(
            session,
            TriggerChunkScopeRequest(
                tenant_id=ctx.tenant_id,
                patient_id=ctx.patient_id,
                chunk_ids=chunk_ids,
                referral_id=ctx.referral_id,
                document_reference_id=ctx.document_reference_id,
            ),
        )
    if not scope.ok:
        first = scope.errors[0].message if scope.errors else "Chunk scope validation failed."
        raise DocumentRunError(first)

    run_id = uuid.uuid4().hex
    body = build_referral_received_message(
        patient_id=ctx.patient_id,
        encounter_id=ctx.encounter_id,
        referral_id=ctx.referral_id,
        document_reference_id=ctx.document_reference_id,
        chunk_ids=list(scope.ordered_chunk_ids),
        run_id=run_id,
        plan_definition_id=plan_id or DEFAULT_PLAN_ID,
        context={
            "source": "patient-viewer",
            "referral_id": ctx.referral_id,
            "document_reference_id": ctx.document_reference_id,
        },
    )
    body["tenant_id"] = ctx.tenant_id
    body["capture_validation_output"] = True
    if requested_by:
        body["requested_by"] = requested_by

    sender = publish if publish is not None else default_publish
    error_message = ""
    status = "queued"
    try:
        sender(body, run_id)
    except Exception as exc:
        logger.warning("patient_document_runs.publish failed: %s", exc)
        error_message = str(exc)
        status = "failed"
    else:
        if eager_durable_bootstrap:
            bootstrap_error = bootstrap_durable_lab_run(body) or ""
            if bootstrap_error:
                error_message = bootstrap_error
                status = "failed"

    pipe = poll_run_status(client, run_id) if status != "failed" else {}
    if pipe.get("status") in ("running", "completed", "failed"):
        status = str(pipe.get("status") or status)
    assessment_id = str(pipe.get("assessment_id") or "")
    stages = list_stage_progress(client, run_id) if status != "failed" else []
    return StartDocumentRunResult(
        run_id=run_id,
        status=status,
        assessment_id=assessment_id,
        error_message=error_message,
        stage_progress=stages,
    )


def refresh_document_run(client: Any, *, run_id: str) -> StartDocumentRunResult:
    pipe = poll_run_status(client, run_id)
    status = str(pipe.get("status") or "queued")
    return StartDocumentRunResult(
        run_id=run_id,
        status=status,
        assessment_id=str(pipe.get("assessment_id") or ""),
        error_message="",
        stage_progress=list_stage_progress(client, run_id),
    )
