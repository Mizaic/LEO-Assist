"""Tests for CodingMode routing and autonomous-mode pipeline behaviour.

Covers:
- CodingMode enum values and env-var parsing
- Pipeline _build_sentences_payload: tier classification wired correctly
- Pipeline _write_coding_decisions: audit nodes created for autonomous mode
- Autonomous mode Tier 3 filtering in _process_encounter
- HITL mode skips CodingDecision writes and Tier 3 filtering
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.api.app.config import CodingMode, get_settings

pytestmark = pytest.mark.skip(
    reason="Legacy CodingPipeline routing tests skipped after WorkflowEngine production cutover."
)


# -- CodingMode enum and config --------------------------------------------


class TestCodingModeEnum:

    def test_hitl_value(self):
        assert CodingMode.HITL.value == "hitl"

    def test_autonomous_value(self):
        assert CodingMode.AUTONOMOUS.value == "autonomous"

    def test_from_string(self):
        assert CodingMode("hitl") == CodingMode.HITL
        assert CodingMode("autonomous") == CodingMode.AUTONOMOUS


class TestCodingModeEnvVar:

    @patch.dict("os.environ", {"CODING_MODE": "autonomous"})
    def test_env_autonomous(self):
        settings = get_settings()
        assert settings.coding_mode == CodingMode.AUTONOMOUS

    @patch.dict("os.environ", {"CODING_MODE": "hitl"})
    def test_env_hitl(self):
        settings = get_settings()
        assert settings.coding_mode == CodingMode.HITL

    @patch.dict("os.environ", {"CODING_MODE": "invalid_value"})
    def test_invalid_falls_back_to_hitl(self):
        settings = get_settings()
        assert settings.coding_mode == CodingMode.HITL

    @patch.dict("os.environ", {}, clear=False)
    def test_missing_defaults_to_hitl(self):
        import os
        os.environ.pop("CODING_MODE", None)
        settings = get_settings()
        assert settings.coding_mode == CodingMode.HITL


# -- Pipeline payload: tier classification integration ----------------------


class TestPayloadTierClassification:
    """Verify that _build_sentences_payload passes entity attributes through
    classify_tier and attaches results to each term."""

    def _make_pipeline(self, mode: str = "hitl"):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline
        mock_pc = MagicMock()
        mock_kc = MagicMock()
        return CodingPipeline(mock_pc, mock_kc, coding_mode=mode)

    def _make_item(self, assertion="present", normalized="cough"):
        from libs.ner.extractor_contract import ExtractionItem
        return ExtractionItem(
            sentence_id="s0",
            text=normalized,
            span_start=0,
            span_end=len(normalized),
            semantic_tag="finding",
            assertion=assertion,
            confidence=0.95,
            normalized=normalized,
        )

    def _make_extractor(self):
        ext = MagicMock()
        ext.source = "llm"
        ext.model_name = "test-model"
        ext.model_version = "1.0"
        return ext

    def test_present_high_score_gets_tier1(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk

        pipeline = self._make_pipeline("autonomous")
        sentences = [SentenceChunk(sentence_id="s0", text="cough", start=0, end=5)]
        extracted = {"s0": [self._make_item()]}
        resolved = {"cough": [{"snomed_concept_id": "123", "score": 0.96, "surface_form_status": "approved"}]}

        payload = pipeline._build_sentences_payload(
            sentences, extracted, resolved, self._make_extractor(),
        )
        term = payload[0]["terms"][0]
        assert term["decision_tier"] == 1
        assert term["tier_decision"] == "auto_coded"
        assert term["audit_flag"] is False

    def test_absent_assertion_gets_tier3(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk

        pipeline = self._make_pipeline("autonomous")
        sentences = [SentenceChunk(sentence_id="s0", text="no cough", start=0, end=8)]
        extracted = {"s0": [self._make_item(assertion="absent")]}
        resolved = {"cough": [{"snomed_concept_id": "123", "score": 0.96, "surface_form_status": "approved"}]}

        payload = pipeline._build_sentences_payload(
            sentences, extracted, resolved, self._make_extractor(),
        )
        term = payload[0]["terms"][0]
        assert term["decision_tier"] == 3
        assert term["tier_decision"] == "not_coded"

    def test_medium_score_autonomous_gets_audit_flag(self):
        from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk

        pipeline = self._make_pipeline("autonomous")
        sentences = [SentenceChunk(sentence_id="s0", text="cough", start=0, end=5)]
        extracted = {"s0": [self._make_item()]}
        resolved = {"cough": [{"snomed_concept_id": "123", "score": 0.80, "surface_form_status": ""}]}

        payload = pipeline._build_sentences_payload(
            sentences, extracted, resolved, self._make_extractor(),
        )
        term = payload[0]["terms"][0]
        assert term["decision_tier"] == 2
        assert term["audit_flag"] is True
        assert term["tier_decision"] == "coded_with_flag"


# -- Autonomous CodingDecision writes --------------------------------------


class TestWriteCodingDecisions:

    def test_writes_one_decision_per_term(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        mock_pc = MagicMock()
        mock_session = MagicMock()
        mock_pc.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_pc.session.return_value.__exit__ = MagicMock(return_value=False)

        pipeline = CodingPipeline(mock_pc, MagicMock(), coding_mode="autonomous")

        sentences_payload = [
            {
                "sentence_id": "s0",
                "terms": [
                    {
                        "text": "cough",
                        "semantic_tag": "finding",
                        "assertion": "present",
                        "decision_tier": 1,
                        "tier_decision": "auto_coded",
                        "tier_reason": "high_confidence",
                        "coding": {"score": 0.96},
                    },
                    {
                        "text": "diabetes",
                        "semantic_tag": "disorder",
                        "assertion": "present",
                        "decision_tier": 2,
                        "tier_decision": "coded_with_flag",
                        "tier_reason": "medium_confidence",
                        "coding": {"score": 0.80},
                    },
                ],
            },
        ]

        pipeline._write_coding_decisions("enc-001", "pat-hash", sentences_payload)
        assert mock_session.run.call_count == 2

    def test_decision_id_format(self):
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        mock_pc = MagicMock()
        mock_session = MagicMock()
        mock_pc.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_pc.session.return_value.__exit__ = MagicMock(return_value=False)

        pipeline = CodingPipeline(mock_pc, MagicMock(), coding_mode="autonomous")

        sentences_payload = [
            {
                "sentence_id": "s0",
                "terms": [
                    {
                        "text": "test",
                        "semantic_tag": "finding",
                        "assertion": "present",
                        "decision_tier": 1,
                        "tier_decision": "auto_coded",
                        "tier_reason": "high_confidence",
                        "coding": {"score": 0.96},
                    },
                ],
            },
        ]
        pipeline._write_coding_decisions("enc-42", "pat-x", sentences_payload)
        call_kwargs = mock_session.run.call_args
        assert call_kwargs.kwargs["decision_id"] == "dec:enc-42:0"

    def test_swallows_neo4j_exception(self):
        """Safety: a single failed write should not crash the pipeline."""
        from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

        mock_pc = MagicMock()
        mock_session = MagicMock()
        mock_session.run.side_effect = RuntimeError("Neo4j write failed")
        mock_pc.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_pc.session.return_value.__exit__ = MagicMock(return_value=False)

        pipeline = CodingPipeline(mock_pc, MagicMock(), coding_mode="autonomous")
        sentences_payload = [
            {
                "sentence_id": "s0",
                "terms": [{"text": "t", "semantic_tag": "f", "assertion": "present",
                           "decision_tier": 1, "tier_decision": "auto_coded",
                           "tier_reason": "test", "coding": {"score": 0.9}}],
            },
        ]
        pipeline._write_coding_decisions("e", "p", sentences_payload)
