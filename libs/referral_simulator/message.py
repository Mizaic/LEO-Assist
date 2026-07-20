"""Build production-shaped referral-received bus messages."""

from __future__ import annotations

from typing import Any


class ReferralSimulatorError(ValueError):
    """Invalid referral simulator input."""


def build_referral_received_message(
    *,
    patient_id: str,
    encounter_id: str,
    referral_id: str,
    document_reference_id: str,
    chunk_ids: list[str],
    run_id: str,
    plan_definition_id: str = "pd-referral-assessment",
    guideline_id: str | None = None,
    completeness_domain: str | None = None,
    completeness_subdomain: str | None = None,
    guideline_ruleset_version: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a referral-received body with required chunk handoff fields.

    `guideline_ruleset_version` is an optional per-run override so a
    candidate (unactivated) guideline bitmap can be tested end-to-end
    without touching the live "current version" pointer used by real
    traffic -- see libs/pipeline_graph/subgraphs/compliance.py.
    """
    if not chunk_ids:
        raise ReferralSimulatorError("chunk_ids must be non-empty")
    if not str(referral_id or "").strip():
        raise ReferralSimulatorError("referral_id is required")
    if not str(document_reference_id or "").strip():
        raise ReferralSimulatorError("document_reference_id is required")
    if not str(patient_id or "").strip():
        raise ReferralSimulatorError("patient_id is required")

    merged_context: dict[str, Any] = dict(context or {})
    merged_context["referral_id"] = referral_id

    body: dict[str, Any] = {
        "event_type": "referral-received",
        "plan_definition_id": plan_definition_id,
        "workflow_id": plan_definition_id,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "referral_id": referral_id,
        "document_reference_id": document_reference_id,
        "chunk_ids": list(chunk_ids),
        "text_segmentation_mode": "document_chunks",
        "run_id": run_id,
        "mode": "referral_assessment",
        "output_target": "patient_graph",
        "source_node_type": "ReferralRequest",
        "source_node_id": referral_id,
        "dry_run": False,
        "context": merged_context,
    }
    if guideline_id:
        body["guideline_id"] = guideline_id
        body["guideline_scope_type"] = "guideline"
        body["guideline_scope_id"] = guideline_id
    if completeness_domain:
        body["completeness_domain"] = completeness_domain
    if completeness_subdomain:
        body["completeness_subdomain"] = completeness_subdomain
    if guideline_ruleset_version:
        body["guideline_ruleset_version"] = guideline_ruleset_version
    return body
