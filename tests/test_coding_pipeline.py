"""Tests for services/coding-worker/app/pipeline/pipeline_service.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.skip(
    reason="Legacy CodingPipeline unit tests skipped after WorkflowEngine production cutover."
)


class TestPipelineStats:

    def test_initial_values(self):
        from services.coding_worker.app.pipeline.pipeline_service import PipelineStats

        stats = PipelineStats()
        assert stats.processed_encounters == 0
        assert stats.queued_for_review == 0
        assert stats.rejected_hard_fail == 0

    def test_record_hard_fail(self):
        from services.coding_worker.app.pipeline.pipeline_service import PipelineStats

        stats = PipelineStats()
        stats.record(hard_fails=True, warnings=False)
        assert stats.processed_encounters == 1
        assert stats.rejected_hard_fail == 1
        assert stats.warnings_only == 0

    def test_record_warnings(self):
        from services.coding_worker.app.pipeline.pipeline_service import PipelineStats

        stats = PipelineStats()
        stats.record(hard_fails=False, warnings=True)
        assert stats.warnings_only == 1

    def test_record_clean(self):
        from services.coding_worker.app.pipeline.pipeline_service import PipelineStats

        stats = PipelineStats()
        stats.record(hard_fails=False, warnings=False)
        assert stats.processed_encounters == 1
        assert stats.rejected_hard_fail == 0
        assert stats.warnings_only == 0

    def test_snapshot(self):
        from services.coding_worker.app.pipeline.pipeline_service import PipelineStats

        stats = PipelineStats()
        stats.record(True, False)
        snap = stats.snapshot()
        assert snap["processed_encounters"] == 1
        assert snap["rejected_hard_fail"] == 1


class TestCodingPipelineResolve:

    @pytest.mark.asyncio
    async def test_resolve_empty_terms(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        mock_pc = MagicMock()
        mock_kc = MagicMock()
        with (
            patch(
                "services.coding_worker.app.pipeline.pipeline_service.SentenceSplitter"
            ),
            patch("services.coding_worker.app.pipeline.pipeline_service.LLMExtractor"),
        ):
            pipeline = CodingPipeline(mock_pc, mock_kc)

        result = await pipeline._resolve_via_api([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolve_deduplicates_terms(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        mock_pc = MagicMock()
        mock_kc = MagicMock()
        with (
            patch(
                "services.coding_worker.app.pipeline.pipeline_service.SentenceSplitter"
            ),
            patch("services.coding_worker.app.pipeline.pipeline_service.LLMExtractor"),
        ):
            pipeline = CodingPipeline(mock_pc, mock_kc)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {"cough": [{"snomed_concept_id": "123"}]}
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await pipeline._resolve_via_api(["cough", "cough", "cough"])
        assert "cough" in result


class TestBuildSentencesPayload:

    def test_builds_correct_structure(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk
        from services.coding_worker.app.pipeline.llm_extractor import ExtractedTerm

        mock_pc = MagicMock()
        mock_kc = MagicMock()
        with (
            patch(
                "services.coding_worker.app.pipeline.pipeline_service.SentenceSplitter"
            ),
            patch("services.coding_worker.app.pipeline.pipeline_service.LLMExtractor"),
        ):
            pipeline = CodingPipeline(mock_pc, mock_kc)

        sentences = [
            SentenceChunk(sentence_id="s0", text="Has cough.", start=0, end=10)
        ]
        extracted = {
            "s0": [
                ExtractedTerm(
                    sentence_id="s0",
                    text="cough",
                    lookup_term="cough",
                    semantic_tag="finding",
                    assertion="present",
                    context={"negated": False},
                    modifiers={},
                ),
            ]
        }
        resolved = {
            "cough": [
                {"snomed_concept_id": "49727002", "snomed_term": "Cough", "score": 0.95}
            ]
        }

        payload = pipeline._build_sentences_payload(sentences, extracted, resolved)
        assert len(payload) == 1
        assert payload[0]["sentence_id"] == "s0"
        assert payload[0]["text"] == "Has cough."
        assert len(payload[0]["terms"]) == 1
        assert payload[0]["terms"][0]["coding"]["snomed_concept_id"] == "49727002"

    def test_handles_no_resolved_match(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk
        from services.coding_worker.app.pipeline.llm_extractor import ExtractedTerm

        mock_pc = MagicMock()
        mock_kc = MagicMock()
        with (
            patch(
                "services.coding_worker.app.pipeline.pipeline_service.SentenceSplitter"
            ),
            patch("services.coding_worker.app.pipeline.pipeline_service.LLMExtractor"),
        ):
            pipeline = CodingPipeline(mock_pc, mock_kc)

        sentences = [SentenceChunk(sentence_id="s0", text="Unknown.", start=0, end=8)]
        extracted = {
            "s0": [
                ExtractedTerm(
                    sentence_id="s0",
                    text="rare_thing",
                    lookup_term="rare_thing",
                    semantic_tag="finding",
                    assertion="present",
                    context={},
                    modifiers={},
                ),
            ]
        }

        payload = pipeline._build_sentences_payload(sentences, extracted, {})
        term = payload[0]["terms"][0]
        assert term["coding"]["snomed_concept_id"] is None
        assert term["coding"]["score"] == 0.0


class TestCodingPipelineEmit:

    def test_emit_calls_hook(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        hook = MagicMock()
        CodingPipeline._emit(hook, {"type": "test"})
        hook.assert_called_once_with({"type": "test"})

    def test_emit_none_hook(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        CodingPipeline._emit(None, {"type": "test"})


class TestProgressPublisher:

    @patch("services.coding_worker.app.services.progress_publisher._get_redis")
    def test_publish_progress(self, mock_get_redis):
        from services.coding_worker.app.services.progress_publisher import (
            publish_progress,
        )

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        publish_progress("run-123", {"type": "test_event"})
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "pipeline:run-123"

    @patch("services.coding_worker.app.services.progress_publisher._get_redis")
    def test_publish_swallows_exceptions(self, mock_get_redis):
        from services.coding_worker.app.services.progress_publisher import (
            publish_progress,
        )

        mock_get_redis.side_effect = Exception("redis down")
        publish_progress("run-123", {"type": "test_event"})
