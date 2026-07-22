"""Gate 3 E3.1-E3.3 -- bounded recall tools and preflight."""

from __future__ import annotations

from libs.sbar.recall_preflight import (
    RecallBudget,
    check_recall_budget,
    preflight_recall,
    recall_policy_from_manifest,
)
from libs.sbar.recall_tools import RecallScope, RecallToolRegistry
from libs.workflow.execution_manifest import build_execution_manifest
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY


def test_fetch_chunk_rejects_out_of_manifest_chunk() -> None:
    scope = RecallScope(
        tenant_id="t1",
        patient_id="p1",
        referral_id="rr-1",
        run_id="run-1",
        allowed_chunk_ids=frozenset({"c1"}),
    )
    registry = RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: [],
        fetch_chunk=lambda cid: {"id": cid, "text": "secret"},
        find_referral_reason=lambda: None,
    )
    assert registry.fetch_chunk_scoped("c2") is None
    assert registry.fetch_count == 0
    assert registry.audit_log[-1]["tool_result"]["error"] == "chunk_out_of_manifest"


def test_preflight_only_triggers_for_approved_conditions() -> None:
    result = preflight_recall(
        missing_slots=["missing_referral_reason", "unsupported_slot"],
        coverage_gaps=0,
    )
    assert result.should_recall is True
    assert result.reasons == ["missing_referral_reason"]


def test_budget_exhaustion_sets_needs_review_flags() -> None:
    result = check_recall_budget(
        chunk_fetches=5,
        llm_calls=2,
        tokens_used=50000,
        budget=RecallBudget(max_chunk_fetches=5, max_llm_calls=2, max_tokens=50000),
    )
    assert result.exhausted is True
    assert result.needs_review is True
    assert "RECALL_CHUNK_FETCH_LIMIT" in result.missing_flags


def test_execution_manifest_carries_bounded_recall_policy() -> None:
    manifest = build_execution_manifest(
        PlanManifest(
            plan_id="pd-referral-assessment",
            version_id=1,
            version_node_id="v1",
            policy_version="v1",
            workflow_mode="durable_pubsub",
            actions=(),
            referral_policy=dict(DEFAULT_REFERRAL_POLICY),
        ),
        prompt_hashes={
            "situation": "a",
            "background": "b",
            "recommendation": "c",
            "recall": "d",
        },
        model_config={"key": "aws:big"},
    )
    recall = recall_policy_from_manifest(manifest)
    assert recall.max_chunk_fetches == 5
    assert recall.max_llm_calls == 2
    assert recall.max_tokens == 50000
    assert DEFAULT_REFERRAL_POLICY["prompts"]["recall"]["name"] == "sbar_recall"
