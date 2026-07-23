"""Mandatory SBAR audit persistence preconditions (M2.8).

Atlas trace:
  DO: DO-025F8C6C
  DI: DI-075775FF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-025F8C6C")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AuditPersistenceError(RuntimeError):
    """Raised when mandatory audit evidence cannot be persisted."""


@dataclass(frozen=True)
class AuditProvenanceBundle:
    execution_manifest: dict[str, Any]
    prompt_provenance: dict[str, Any] = field(default_factory=dict)
    model_provenance: dict[str, Any] = field(default_factory=dict)
    source_accounting: dict[str, Any] = field(default_factory=dict)
    audit_event_id: str = ""


def validate_completion_preconditions(bundle: AuditProvenanceBundle) -> list[str]:
    """Return human-readable blockers for a completed Assessment."""
    errors: list[str] = []
    manifest = bundle.execution_manifest or {}
    if not manifest:
        errors.append("execution_manifest_missing")
    if not str(manifest.get("plan_version_id") or manifest.get("policy_version") or ""):
        errors.append("execution_manifest_incomplete")

    prompts = manifest.get("prompts") or {}
    if not isinstance(prompts, dict) or not prompts:
        errors.append("prompt_provenance_missing")
    else:
        for stage, pin in prompts.items():
            if not str((pin or {}).get("content_hash") or ""):
                errors.append(f"prompt_hash_missing:{stage}")

    model = manifest.get("model") or bundle.model_provenance or {}
    if not str(model.get("key") or model.get("modelId") or ""):
        errors.append("model_provenance_missing")

    accounting = bundle.source_accounting or {}
    if not accounting:
        errors.append("source_accounting_missing")
    elif int(accounting.get("total_sentences") or 0) < 0:
        errors.append("source_accounting_invalid")

    if not str(bundle.audit_event_id or "").strip():
        errors.append("audit_link_missing")
    return errors


def completion_status_from_preconditions(
    *,
    stage_errors: list[str],
    bundle: AuditProvenanceBundle,
) -> tuple[str, list[str]]:
    """Map audit blockers to a non-completed Assessment status."""
    blockers = validate_completion_preconditions(bundle)
    combined = list(stage_errors) + blockers
    if combined:
        return "draft", combined
    return "completed", []


def require_audit_persisted(
    bundle: AuditProvenanceBundle,
    *,
    write_ok: bool,
    audit_event_id: str,
) -> None:
    """Fail closed when mandatory audit persistence did not succeed."""
    if not write_ok or not str(audit_event_id or "").strip():
        blockers = validate_completion_preconditions(
            AuditProvenanceBundle(
                execution_manifest=bundle.execution_manifest,
                prompt_provenance=bundle.prompt_provenance,
                model_provenance=bundle.model_provenance,
                source_accounting=bundle.source_accounting,
                audit_event_id=audit_event_id,
            )
        )
        detail = ", ".join(blockers) or "audit_persistence_failed"
        raise AuditPersistenceError(detail)
