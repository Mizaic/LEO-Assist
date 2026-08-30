"""Unit tests for libs/pipeline_graph/subgraphs/sbar.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_sbar_subgraph_compiles():
    from libs.pipeline_graph.subgraphs.sbar import build_sbar_subgraph

    sg = build_sbar_subgraph()
    assert sg is not None


def test_sbar_run_returns_assessment_id():
    # Patch the async function itself -- avoids creating an unawaited coroutine.
    async def _mock_async(_state):
        return {
            "sbar_assessment_id": "assess-123",
            "sbar_status": "completed",
            "errors": [],
            "review_status": "pending_review",
        }

    from libs.pipeline_graph.subgraphs.sbar import _run_sbar

    with patch("libs.pipeline_graph.subgraphs.sbar._async_run_sbar", _mock_async):
        result = _run_sbar(
            {
                "patient_id": "p-1",
                "encounter_id": "e-1",
                "run_id": "r-1",
                "guideline_ids": ["g-1"],
            }
        )
    assert result["sbar_assessment_id"] == "assess-123"
    assert result["review_status"] == "pending_review"


def test_sbar_run_handles_exception():
    async def _mock_async(_state):
        raise RuntimeError("orchestrator failed")

    from libs.pipeline_graph.subgraphs.sbar import _run_sbar

    with patch("libs.pipeline_graph.subgraphs.sbar._async_run_sbar", _mock_async):
        result = _run_sbar({"encounter_id": "e-1", "run_id": "r-1"})
    assert result["sbar_status"] == "error"
    assert any("orchestrator failed" in e for e in result.get("errors", []))


def test_assessment_id_is_deterministic():
    from libs.pipeline_graph.subgraphs.sbar import _assessment_id

    id1 = _assessment_id("run-abc", "enc-xyz")
    id2 = _assessment_id("run-abc", "enc-xyz")
    id3 = _assessment_id("run-abc", "enc-different")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 32


def test_sbar_loads_pinned_manifest_from_pipeline_run() -> None:
    """Durable flow pins the manifest on PipelineRun, not the subgraph TypedDict.

    Production minus pub/sub still admits the run with a full execution
    manifest. SBAR must load that pin when state omits it, or audit
    fail-closed marks a finished letter as failed.
    """
    from libs.pipeline_graph.subgraphs.sbar import _resolve_sbar_policy_runtime
    from libs.sbar.policy_runtime import build_runtime
    from libs.workflow.execution_manifest import build_execution_manifest
    from libs.workflow.plan_manifest import PlanManifest
    from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY

    manifest = build_execution_manifest(
        PlanManifest(
            plan_id="pd-referral-assessment",
            version_id=1,
            version_node_id="ver-1",
            policy_version="v6",
            workflow_mode="durable_pubsub",
            actions=(),
            referral_policy=dict(DEFAULT_REFERRAL_POLICY),
        ),
        prompt_hashes={
            "situation": "h1",
            "background": "h2",
            "recommendation": "h3",
            "recall": "h4",
        },
        model_config={
            "key": "azure:small",
            "provider": "azure",
            "tier": "small",
            "modelId": "gpt-5-mini",
        },
    )

    with patch(
        "libs.sbar.policy_runtime.load_execution_manifest",
        return_value=manifest,
    ), patch("libs.neo4j_client.client.PatientGraphClient") as client_cls:
        client_cls.return_value = MagicMock()
        runtime = _resolve_sbar_policy_runtime({"run_id": "run-prod-1"})

    assert runtime is not None
    assert runtime.execution_manifest["plan_version_id"] == "ver-1"
    assert runtime.model_key == "azure:small"
    expected = build_runtime(manifest)
    assert (
        runtime.execution_manifest["prompts"]
        == expected.execution_manifest["prompts"]
    )


def test_partition_pipeline_messages_keeps_audit_blockers_as_errors() -> None:
    from libs.pipeline_graph.subgraphs.sbar import _partition_pipeline_messages

    errors, warnings = _partition_pipeline_messages(
        [
            "situation:LLM timeout",
            "audit:execution_manifest_missing, audit_link_missing",
            "audit_link_missing",
            "prompt_hash_missing:situation",
        ]
    )
    assert "situation:LLM timeout" in errors
    assert any("audit_link_missing" in item for item in errors)
    assert warnings == []
