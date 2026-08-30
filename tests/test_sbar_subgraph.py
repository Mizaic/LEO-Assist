"""Unit tests for libs/pipeline_graph/subgraphs/sbar.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


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
