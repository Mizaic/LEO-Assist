"""Tests for libs/coding/haiku_arbitrator.py.

All tests are offline (no live API calls). The LLMClient is mocked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from libs.coding.haiku_arbitrator import (
    HaikuArbitrator,
    ArbitrationResult,
    _SYSTEM_PROMPT,
    _parse_response,
    _format_candidates,
)


# ---------------------------------------------------------------------------
# System prompt content checks
# ---------------------------------------------------------------------------

class TestSystemPromptContents:
    def test_contains_procedure_rule(self):
        assert "PROCEDURE" in _SYSTEM_PROMPT
        assert "test name span ONLY" in _SYSTEM_PROMPT

    def test_contains_observable_entity_rule(self):
        assert "OBSERVABLE_ENTITY" in _SYSTEM_PROMPT
        assert "test name + value + unit" in _SYSTEM_PROMPT

    def test_contains_finding_rule(self):
        assert "FINDING" in _SYSTEM_PROMPT
        assert "interpretation phrase" in _SYSTEM_PROMPT

    def test_contains_all_interpretation_mappings(self):
        assert "above reference range" in _SYSTEM_PROMPT.lower()
        assert "below reference range" in _SYSTEM_PROMPT.lower()
        assert "within reference range" in _SYSTEM_PROMPT.lower()
        assert "outside reference range" in _SYSTEM_PROMPT.lower()
        assert "borderline" in _SYSTEM_PROMPT.lower()

    def test_contains_all_decision_options(self):
        for decision in ("accept", "fix_snomed", "fix_span", "drop"):
            assert decision in _SYSTEM_PROMPT

    def test_contains_json_output_instruction(self):
        assert "JSON" in _SYSTEM_PROMPT
        assert '"decision"' in _SYSTEM_PROMPT

    def test_no_user_controllable_instructions(self):
        # Verify the system prompt is not templated with user-supplied data.
        assert "{lab_line}" not in _SYSTEM_PROMPT
        assert "{entity_text}" not in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parses_valid_json_object(self):
        text = '{"decision": "accept", "reason": "exact match"}'
        result = _parse_response(text)
        assert result["decision"] == "accept"

    def test_extracts_json_from_prose(self):
        text = 'Here is my answer:\n{"decision": "fix_snomed", "concept_id": "12345"}'
        result = _parse_response(text)
        assert result["decision"] == "fix_snomed"
        assert result["concept_id"] == "12345"

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError, match="no JSON object"):
            _parse_response("Sorry, I cannot help with that.")

    def test_raises_on_malformed_json(self):
        with pytest.raises(Exception):
            _parse_response('{"decision": "accept"')  # unclosed

    def test_extracts_nested_json(self):
        text = '{"decision": "drop", "reason": "no suitable concept"}'
        result = _parse_response(text)
        assert result["decision"] == "drop"


# ---------------------------------------------------------------------------
# Candidate formatter
# ---------------------------------------------------------------------------

class TestFormatCandidates:
    def test_formats_candidates(self):
        candidates = [
            {"concept_id": "123", "snomed_term": "Haemoglobin measurement (procedure)",
             "semantic_tag": "procedure", "score": 1.2},
        ]
        output = _format_candidates(candidates)
        assert "123" in output
        assert "Haemoglobin measurement" in output
        assert "procedure" in output

    def test_empty_candidates_returns_placeholder(self):
        output = _format_candidates([])
        assert "no candidates" in output

    def test_top_n_limit(self):
        candidates = [
            {"concept_id": str(i), "snomed_term": f"Term {i}",
             "semantic_tag": "finding", "score": 0.9}
            for i in range(20)
        ]
        output = _format_candidates(candidates, top_n=5)
        assert "Term 4" in output
        assert "Term 5" not in output


# ---------------------------------------------------------------------------
# HaikuArbitrator (mocked LLM)
# ---------------------------------------------------------------------------

def _make_mock_llm(response_text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_llm = MagicMock()
    mock_llm.converse.return_value = mock_response
    return mock_llm


class TestHaikuArbitrator:
    def _make_arbitrator(self, response_text: str) -> HaikuArbitrator:
        arb = HaikuArbitrator.__new__(HaikuArbitrator)
        arb._llm = _make_mock_llm(response_text)
        return arb

    def test_accept_decision(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "accept", "concept_id": "271026005",
                        "snomed_term": "Haemoglobin measurement", "reason": "exact"})
        )
        result = arb.arbitrate(
            lab_line="Haemoglobin (Xa96v) 135 g/L [130-170]",
            numeric_value="135", unit="g/L",
            reference_range="[130-170]", interpretation="",
            entity_label="procedure", entity_text="Haemoglobin",
            candidates=[],
        )
        assert result.decision == "accept"
        assert result.concept_id == "271026005"
        assert result.is_accepted

    def test_fix_snomed_decision(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "fix_snomed", "concept_id": "999999",
                        "snomed_term": "Better concept", "reason": "better match"})
        )
        result = arb.arbitrate(
            lab_line="Haemoglobin (Xa96v) 135 g/L [130-170] - Normal",
            numeric_value="135", unit="g/L",
            reference_range="[130-170]", interpretation="Normal",
            entity_label="finding", entity_text="Haemoglobin 135 g/L [130-170] - Normal",
            candidates=[],
        )
        assert result.decision == "fix_snomed"
        assert result.concept_id == "999999"
        assert result.is_accepted

    def test_drop_decision(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "drop", "reason": "no suitable concept"})
        )
        result = arb.arbitrate(
            lab_line="Some test (XYZ) 5.0 units",
            numeric_value="5.0", unit="units",
            reference_range="", interpretation="",
            entity_label="finding", entity_text="Some test finding",
            candidates=[],
        )
        assert result.is_drop
        assert not result.is_accepted

    def test_fix_span_uses_returned_text(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "fix_span", "text": "Corrected span",
                        "concept_id": "123", "reason": "span too long"})
        )
        result = arb.arbitrate(
            lab_line="Some test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Some test (Xa1)",
            candidates=[],
        )
        assert result.decision == "fix_span"
        assert result.text == "Corrected span"

    def test_invalid_decision_falls_back_to_drop(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "INVALID", "reason": "bad"})
        )
        result = arb.arbitrate(
            lab_line="Some test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Some test",
            candidates=[],
        )
        assert result.is_drop

    def test_llm_error_returns_drop(self):
        arb = HaikuArbitrator.__new__(HaikuArbitrator)
        mock_llm = MagicMock()
        mock_llm.converse.side_effect = RuntimeError("connection refused")
        arb._llm = mock_llm

        result = arb.arbitrate(
            lab_line="Test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Test",
            candidates=[],
        )
        assert result.is_drop
        assert result.reason == "arbitrator_error"

    def test_malformed_json_returns_drop(self):
        arb = self._make_arbitrator("Sorry, I cannot help with that.")
        result = arb.arbitrate(
            lab_line="Test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Test",
            candidates=[],
        )
        assert result.is_drop

    def test_user_message_contains_lab_line(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "accept", "concept_id": "1", "snomed_term": "X"})
        )
        lab_line = "Haemoglobin (Xa96v) 135 g/L [130-170] - Normal"
        arb.arbitrate(
            lab_line=lab_line,
            numeric_value="135", unit="g/L",
            reference_range="[130-170]", interpretation="Normal",
            entity_label="procedure", entity_text="Haemoglobin",
            candidates=[],
        )
        call_args = arb._llm.converse.call_args
        user_content = call_args.kwargs["messages"][0]["content"]
        assert lab_line in user_content

    def test_system_prompt_passed_unchanged(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "accept", "concept_id": "1", "snomed_term": "X"})
        )
        arb.arbitrate(
            lab_line="Test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Test",
            candidates=[],
        )
        call_args = arb._llm.converse.call_args
        assert call_args.kwargs["system"] is _SYSTEM_PROMPT

    def test_agent_task_label(self):
        arb = self._make_arbitrator(
            json.dumps({"decision": "accept", "concept_id": "1", "snomed_term": "X"})
        )
        arb.arbitrate(
            lab_line="Test (Xa1) 5.0 g/L",
            numeric_value="5.0", unit="g/L",
            reference_range="", interpretation="",
            entity_label="procedure", entity_text="Test",
            candidates=[],
        )
        call_args = arb._llm.converse.call_args
        assert call_args.kwargs["agent_task"] == "lab_snomed_arbitration"
