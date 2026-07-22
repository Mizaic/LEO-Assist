"""Tests for pinned PlanDefinitionVersion manifest loading (M2.1)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from libs.workflow.plan_manifest import (
    PlanManifest,
    load_plan_manifest,
    parse_actions_from_snapshot,
    policy_version_label,
)

_SAMPLE_PLAN = {
    "id": "pd-referral-assessment",
    "resourceType": "PlanDefinition",
    "status": "active",
    "_workflowMode": "durable_pubsub",
    "action": [
        {
            "id": "act-trigger",
            "_sequence": 0,
            "_subgraphId": "trigger",
            "_nodeType": "trigger",
            "trigger": [{"type": "data-changed", "name": "referral-received"}],
        },
        {
            "id": "act-extract",
            "_sequence": 1,
            "_subgraphId": "extraction",
            "_dynamicValues": {"model_tier": "small"},
            "relatedAction": [{"actionId": "act-trigger"}],
        },
    ],
}


def test_parse_actions_from_snapshot_trigger_and_subgraph() -> None:
    actions = parse_actions_from_snapshot(_SAMPLE_PLAN)
    assert len(actions) == 2
    assert actions[0].trigger_name == "referral-received"
    assert actions[0].node_type == "trigger"
    assert actions[1].subgraph_id == "extraction"
    assert actions[1].config.get("model_tier") == "small"


def test_policy_version_label() -> None:
    assert policy_version_label(3) == "v3"


def test_load_plan_manifest_latest_version() -> None:
    raw = json.dumps(_SAMPLE_PLAN)
    mock_kg = MagicMock()
    mock_kg.run.return_value = [
        {
            "version_node_id": "ver-uuid-9",
            "version_id": 9,
            "raw_json": raw,
            "workflow_mode": "durable_pubsub",
        }
    ]
    mock_kg.close = MagicMock()

    with patch(
        "libs.workflow.plan_manifest.KnowledgeGraphClient",
        return_value=mock_kg,
    ):
        manifest = load_plan_manifest("pd-referral-assessment", policy_version="latest")

    assert isinstance(manifest, PlanManifest)
    assert manifest.version_id == 9
    assert manifest.version_node_id == "ver-uuid-9"
    assert manifest.policy_version == "v9"
    assert len(manifest.actions) == 2
    mock_kg.close.assert_called_once()


def test_load_plan_manifest_specific_version() -> None:
    raw = json.dumps(_SAMPLE_PLAN)
    mock_kg = MagicMock()
    mock_kg.run.return_value = [
        {
            "version_node_id": "ver-uuid-2",
            "version_id": 2,
            "raw_json": raw,
            "workflow_mode": "durable_pubsub",
        }
    ]
    mock_kg.close = MagicMock()

    with patch(
        "libs.workflow.plan_manifest.KnowledgeGraphClient",
        return_value=mock_kg,
    ):
        manifest = load_plan_manifest("pd-referral-assessment", policy_version="v2")

    assert manifest.version_id == 2
    assert manifest.policy_version == "v2"
    call_kw = mock_kg.run.call_args.kwargs
    assert call_kw["policy_version"] == "v2"
