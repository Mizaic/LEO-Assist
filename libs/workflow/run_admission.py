"""Deterministic pipeline run admission keys (D1.1).

Atlas trace:
  DI: DI-0CB9E932
  DO: DO-7EE5D7A6
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-0CB9E932")
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from libs.pipeline.document_chunk_loader import merge_referral_message_fields
from libs.workflow.durable_steps import StepRequest


def build_admission_key(body: dict[str, Any]) -> str:
    """Hash tenant, patient, referral scope, ordered inputs and workflow version.

    Validation Lab re-Test sends the same patient/chunks as a prior run. Include
    the Lab ``run_id`` in the key when ``context.source == validation-lab`` so
    each Test admits a distinct PipelineRun instead of no-opping against a
    completed admission (DI-2289D095).
    """
    request = StepRequest.from_message(body)
    context = merge_referral_message_fields(body)
    body_context = body.get("context") if isinstance(body.get("context"), dict) else {}
    chunk_ids = context.get("chunk_ids") or body.get("chunk_ids") or []
    if not isinstance(chunk_ids, list):
        chunk_ids = []
    ordered_chunks = [str(item) for item in chunk_ids]
    chunk_hashes = context.get("chunk_content_hashes") or body.get(
        "chunk_content_hashes"
    )
    if not isinstance(chunk_hashes, list):
        chunk_hashes = []
    payload: dict[str, Any] = {
        "tenant_id": str(request.tenant_id or ""),
        "patient_id": request.patient_id,
        "referral_id": str(context.get("referral_id") or context.get("case_id") or ""),
        "plan_definition_id": str(
            request.plan_definition_id or request.workflow_id or ""
        ),
        "policy_version": str(
            context.get("policy_version") or body.get("policy_version") or "default"
        ),
        "chunk_ids": ordered_chunks,
        "chunk_content_hashes": [str(item) for item in chunk_hashes],
    }
    source = str(body_context.get("source") or context.get("source") or "").strip()
    # validation-lab and validation-lab-ag-run both re-Test the same graph shape.
    if source.startswith("validation-lab"):
        payload["lab_run_id"] = str(body.get("run_id") or request.run_id or "")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
