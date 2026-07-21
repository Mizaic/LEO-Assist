"""Unit tests for libs/pipeline_graph/subgraphs/referral_reason.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_missing_referral_id_skips():
    from libs.pipeline_graph.subgraphs.referral_reason import _extract_reason

    result = _extract_reason({"chunk_ids": ["c1"]})
    assert result.get("referral_reason_skipped") is True


def test_missing_chunk_ids_skips():
    from libs.pipeline_graph.subgraphs.referral_reason import _extract_reason

    result = _extract_reason({"referral_id": "ref-1"})
    assert result.get("referral_reason_skipped") is True


def test_no_matching_chunks_skips():
    # Patch the async function itself -- avoids creating an unawaited coroutine.
    async def _mock_async(*_args, **_kwargs):
        return {"referral_reason_skipped": True}

    from libs.pipeline_graph.subgraphs.referral_reason import _extract_reason

    with patch(
        "libs.pipeline_graph.subgraphs.referral_reason._async_extract_reason",
        _mock_async,
    ):
        result = _extract_reason(
            {"referral_id": "ref-1", "chunk_ids": ["c1"], "run_id": "r-1"}
        )
    assert result.get("referral_reason_skipped") is True


def test_successful_extraction_returns_reason():
    async def _mock_async(*_args, **_kwargs):
        return {"referral_reason": "Suspected pleural mesothelioma."}

    from libs.pipeline_graph.subgraphs.referral_reason import _extract_reason

    with patch(
        "libs.pipeline_graph.subgraphs.referral_reason._async_extract_reason",
        _mock_async,
    ):
        result = _extract_reason(
            {"referral_id": "ref-1", "chunk_ids": ["c1"], "run_id": "r-1"}
        )
    assert result["referral_reason"] == "Suspected pleural mesothelioma."


def test_exception_returns_skipped_with_error():
    async def _mock_async(*_args, **_kwargs):
        raise RuntimeError("LLM timeout")

    from libs.pipeline_graph.subgraphs.referral_reason import _extract_reason

    with patch(
        "libs.pipeline_graph.subgraphs.referral_reason._async_extract_reason",
        _mock_async,
    ):
        result = _extract_reason(
            {"referral_id": "ref-1", "chunk_ids": ["c1"], "run_id": "r-1"}
        )
    assert result.get("referral_reason_skipped") is True
    assert any("LLM timeout" in e for e in result.get("errors", []))


def test_build_referral_reason_subgraph_compiles():
    from libs.pipeline_graph.subgraphs.referral_reason import (
        build_referral_reason_subgraph,
    )

    sg = build_referral_reason_subgraph()
    assert sg is not None
