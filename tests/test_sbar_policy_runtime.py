"""Tests for SBAR policy runtime wiring (M2.3/M2.4)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.sbar.policy_runtime import (
    build_runtime,
    make_llm_invoker,
    make_prompt_fetcher,
    runtime_from_state,
    stage_llm_params,
)
from libs.workflow.execution_manifest import build_execution_manifest
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY


def _manifest_dict() -> dict:
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


def test_runtime_from_state_prefers_dict() -> None:
    manifest = _manifest_dict()
    runtime = runtime_from_state({"execution_manifest": manifest})
    assert runtime is not None
    assert runtime.model_key == "aws:big"


@patch("libs.sbar.policy_runtime.get_prompt", return_value="SYSTEM")
def test_make_prompt_fetcher_uses_manifest_pins(mock_get) -> None:
    runtime = build_runtime(_manifest_dict())
    fetcher = make_prompt_fetcher(runtime)
    text = fetcher("sbar_situation")
    assert text == "SYSTEM"
    mock_get.assert_called_once_with("sbar_situation", version=2)


def test_stage_llm_params_reads_manifest() -> None:
    runtime = build_runtime(_manifest_dict())
    params = stage_llm_params(runtime, "background")
    assert params["max_tokens"] == 1024
    assert params["temperature"] == 0.0


@patch("libs.sbar.policy_runtime.create_llm")
def test_make_llm_invoker_routes_through_factory(mock_create) -> None:
    mock_client = MagicMock()
    mock_client.converse.return_value = MagicMock(
        text='{"situation_markdown":"ok"}',
        model_id="sonnet-test",
    )
    mock_create.return_value = mock_client
    runtime = build_runtime(_manifest_dict())
    invoker = make_llm_invoker(runtime, "situation")

    import asyncio

    raw = asyncio.run(
        invoker("sys", "user", agent_task="sbar_situation", patient_id="p1")
    )
    assert raw["situation_markdown"] == "ok"
    assert raw["_model_config"]["key"] == "aws:big"
    mock_create.assert_called_once_with(provider="azure", tier="big")
