"""Tests for verify_coding_consensus() in libs/llm_client/escalation.py.

Covers:
- Correct verdict returned when consensus agrees
- Mode-aware fail_verdict (hitl=correct, autonomous=uncertain)
- User message includes entity, encounter, and matched concept
- Integration with run_consensus
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from libs.llm_client.consensus import ConsensusResult
from libs.llm_client.escalation import (
    _parse_verify_verdict,
    verify_coding_consensus,
)


class TestParseVerifyVerdict:

    def test_correct(self):
        assert (
            _parse_verify_verdict('{"verdict": "correct", "reason": "ok"}') == "correct"
        )

    def test_incorrect(self):
        assert (
            _parse_verify_verdict('{"verdict": "incorrect", "reason": "bad"}')
            == "incorrect"
        )

    def test_uncertain(self):
        assert (
            _parse_verify_verdict('{"verdict": "uncertain", "reason": "?"}')
            == "uncertain"
        )

    def test_invalid_verdict_returns_empty(self):
        assert _parse_verify_verdict('{"verdict": "maybe", "reason": "?"}') == ""

    def test_empty_json(self):
        assert _parse_verify_verdict("{}") == ""

    def test_non_json(self):
        assert _parse_verify_verdict("not json at all") == ""


class TestVerifyCodingConsensus:

    @patch("libs.llm_client.consensus.run_consensus")
    def test_correct_verdict(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="correct",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_coding_consensus(
            entity_text="cough",
            encounter_text="Patient reports persistent cough.",
            snomed_term="Cough (finding)",
            snomed_concept_id="49727002",
            coding_mode="autonomous",
        )
        assert result == "correct"

    @patch("libs.llm_client.consensus.run_consensus")
    def test_incorrect_verdict(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="incorrect",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_coding_consensus(
            entity_text="weight",
            encounter_text="Body weight 72kg",
            snomed_term="Weight loss (finding)",
            snomed_concept_id="89362005",
        )
        assert result == "incorrect"

    @patch("libs.llm_client.consensus.run_consensus")
    def test_autonomous_fail_verdict_is_uncertain(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="uncertain",
            agreed=False,
            model_ids=["haiku"],
        )
        verify_coding_consensus(
            entity_text="test",
            encounter_text="test",
            snomed_term="test",
            snomed_concept_id="123",
            coding_mode="autonomous",
        )
        call_kwargs = mock_consensus.call_args.kwargs
        assert call_kwargs["fail_verdict"] == "uncertain"

    @patch("libs.llm_client.consensus.run_consensus")
    def test_hitl_fail_verdict_is_correct(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="correct",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        verify_coding_consensus(
            entity_text="test",
            encounter_text="test",
            snomed_term="test",
            snomed_concept_id="123",
            coding_mode="hitl",
        )
        call_kwargs = mock_consensus.call_args.kwargs
        assert call_kwargs["fail_verdict"] == "correct"

    @patch("libs.llm_client.consensus.run_consensus")
    def test_user_msg_includes_concept(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="correct",
            agreed=True,
            model_ids=["h"],
        )
        verify_coding_consensus(
            entity_text="diabetes",
            encounter_text="Type 2 diabetes",
            snomed_term="Diabetes mellitus type 2 (disorder)",
            snomed_concept_id="44054006",
            coding_mode="hitl",
        )
        call_kwargs = mock_consensus.call_args.kwargs
        user_msg = json.loads(call_kwargs["user_msg"])
        assert "44054006" in user_msg["matched_concept"]
        assert "Diabetes mellitus" in user_msg["matched_concept"]

    @patch("libs.llm_client.consensus.run_consensus")
    def test_encounter_text_truncated(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="correct",
            agreed=True,
            model_ids=["h"],
        )
        long_text = "a" * 5000
        verify_coding_consensus(
            entity_text="t",
            encounter_text=long_text,
            snomed_term="t",
            snomed_concept_id="1",
        )
        call_kwargs = mock_consensus.call_args.kwargs
        user_msg = json.loads(call_kwargs["user_msg"])
        assert len(user_msg["encounter_text"]) == 1500
