"""Tests for mandatory SBAR audit persistence (M2.8)."""

from __future__ import annotations

import pytest

from libs.sbar.audit_persistence import (
    AuditPersistenceError,
    AuditProvenanceBundle,
    completion_status_from_preconditions,
    validate_completion_preconditions,
)
from libs.workflow.execution_manifest import build_execution_manifest
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY


def _manifest() -> dict:
    plan = PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=(),
        referral_policy=dict(DEFAULT_REFERRAL_POLICY),
    )
    return build_execution_manifest(
        plan,
        prompt_hashes={
            "situation": "h1",
            "background": "h2",
            "recommendation": "h3",
            "recall": "h4",
        },
        model_config={
            "key": "aws:big",
            "provider": "aws",
            "tier": "big",
            "modelId": "sonnet-test",
        },
    )


def _bundle(
    *, manifest: dict | None = None, audit_event_id: str = "audit-run-1"
) -> AuditProvenanceBundle:
    manifest = manifest if manifest is not None else _manifest()
    return AuditProvenanceBundle(
        execution_manifest=manifest,
        model_provenance=dict(manifest.get("model") or {}),
        source_accounting={
            "source_count": 1,
            "code_count": 2,
            "total_sentences": 2,
            "covered_sentences": 2,
            "uncovered_sentences": 0,
        },
        audit_event_id=audit_event_id,
    )


def test_missing_manifest_blocks_completion() -> None:
    errors = validate_completion_preconditions(_bundle(manifest={}))
    assert "execution_manifest_missing" in errors


def test_missing_prompt_hash_blocks_completion() -> None:
    manifest = _manifest()
    manifest["prompts"]["situation"]["content_hash"] = ""
    errors = validate_completion_preconditions(_bundle(manifest=manifest))
    assert any(err.startswith("prompt_hash_missing:") for err in errors)


def test_missing_audit_link_blocks_completion() -> None:
    errors = validate_completion_preconditions(_bundle(audit_event_id=""))
    assert "audit_link_missing" in errors


def test_complete_bundle_allows_completed_status() -> None:
    status, blockers = completion_status_from_preconditions(
        stage_errors=[],
        bundle=_bundle(),
    )
    assert status == "completed"
    assert blockers == []


def test_missing_provenance_forces_draft_status() -> None:
    status, blockers = completion_status_from_preconditions(
        stage_errors=[],
        bundle=_bundle(manifest={}),
    )
    assert status == "draft"
    assert blockers


def test_audit_persistence_error_carries_blockers() -> None:
    from libs.sbar.audit_persistence import require_audit_persisted

    with pytest.raises(AuditPersistenceError):
        require_audit_persisted(_bundle(manifest={}), write_ok=False, audit_event_id="")


def test_subgraph_completion_fails_without_manifest() -> None:
    from libs.pipeline_graph.subgraphs.sbar import _run_sbar

    output = _run_sbar(
        {
            "patient_id": "p-1",
            "encounter_id": "enc-1",
            "run_id": "run-audit-1",
        }
    )
    assert output.get("sbar_status") in {"draft", "error"}
    assert output.get("errors")
