"""Tests for execution manifest snapshot at admission (M2.5)."""

from __future__ import annotations

import json

from libs.workflow.execution_manifest import (
    build_execution_manifest,
    manifest_from_json,
)
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY


def _plan_manifest() -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=3,
        version_node_id="ver-node-3",
        policy_version="v3",
        workflow_mode="durable_pubsub",
        actions=(),
        referral_policy=dict(DEFAULT_REFERRAL_POLICY),
    )


def test_build_execution_manifest_snapshots_policy_and_prompts() -> None:
    manifest = build_execution_manifest(
        _plan_manifest(),
        prompt_hashes={
            "situation": "abc123",
            "background": "def456",
            "recommendation": "ghi789",
            "recall": "jkl012",
        },
        model_config={
            "key": "aws:big",
            "provider": "aws",
            "tier": "big",
            "modelId": "claude-sonnet",
        },
    )
    assert manifest["plan_version_id"] == "ver-node-3"
    assert manifest["referral_policy"]["extraction"]["windowSize"] == 10
    assert manifest["prompts"]["situation"]["content_hash"] == "abc123"
    assert manifest["model"]["key"] == "aws:big"
    assert manifest["llm"]["situation"]["maxTokens"] == 512


def test_manifest_round_trip_json() -> None:
    raw = build_execution_manifest(
        _plan_manifest(),
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
            "modelId": "m1",
        },
    )
    restored = manifest_from_json(json.dumps(raw))
    assert restored["policy_version"] == "v3"
    assert restored["referral_policy"]["llm"]["background"]["temperature"] == 0.0
