from __future__ import annotations

import json
from unittest.mock import patch

from libs.pipeline_graph.subgraphs.verification import (
    _route_after_evaluate,
    verify_entities,
)


class _DummyResponse:
    def __init__(self, text: str = "", *, tool_uses: list[dict] | None = None, stop_reason: str = "end_turn") -> None:
        self.text = text
        self.tool_uses = tool_uses or []
        self.stop_reason = stop_reason


class _DummyLLM:
    def __init__(self, responses: list[_DummyResponse] | _DummyResponse | str) -> None:
        if isinstance(responses, str):
            self._responses = [_DummyResponse(text=responses)]
        elif isinstance(responses, _DummyResponse):
            self._responses = [responses]
        else:
            self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def converse(self, **kwargs: object) -> _DummyResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("No dummy responses left")
        return self._responses.pop(0)


def _state() -> dict:
    return {
        "encounter_text": "Patient has asthma.",
        "entities": [{"text": "asthma", "label": "disorder", "start": 12, "end": 18}],
        "prompt_config": {"systemPrompt": "Verify entities.\n{encounter_text}\n{entities_json}"},
        "errors": [],
        "extraction_attempts": [],
    }


def test_verify_entities_parses_fenced_json() -> None:
    state = _state()
    raw = """```json
{"is_accurate": true, "confidence": 0.91, "issues": []}
```"""
    with patch("libs.llm_client.factory.create_llm", return_value=_DummyLLM(raw)):
        result = verify_entities(state)

    assert result["verification_result"]["is_accurate"] is True
    assert result["verification_result"]["confidence"] == 0.91
    assert result["verification_prompt"]["prompt_source"] == "state.prompt_config"
    assert result["extraction_attempts"]


def test_verify_entities_can_use_snomed_lookup_tool_before_final_verdict() -> None:
    state = _state()
    llm = _DummyLLM(
        [
            _DummyResponse(
                tool_uses=[
                    {
                        "name": "lookup_snomed",
                        "toolUseId": "tu-1",
                        "input": {"entity_index": 0, "query": "asthma", "expected_label": "disorder"},
                    }
                ],
                stop_reason="tool_use",
            ),
            _DummyResponse(
                tool_uses=[
                    {
                        "name": "verification_result",
                        "toolUseId": "tu-2",
                        "input": {"is_accurate": True, "confidence": 0.92, "issues": [], "corrections": []},
                    }
                ],
                stop_reason="tool_use",
            ),
        ]
    )
    with patch("libs.llm_client.factory.create_llm", return_value=llm), patch(
        "libs.pipeline_graph.subgraphs.verification.TerminologyClient.resolve",
        return_value={
            "asthma": [
                type(
                    "Resolved",
                    (),
                    {
                        "concept_id": "195967001",
                        "term": "Asthma",
                        "semantic_tag": "disorder",
                        "score": 0.98,
                        "read_code": None,
                    },
                )()
            ]
        },
    ):
        result = verify_entities(state)

    assert result["verification_result"]["is_accurate"] is True
    assert result["verification_tool_trace"][0]["tool_name"] == "lookup_snomed"
    assert result["verification_tool_trace"][0]["candidate_count"] == 1
    assert len(llm.calls) == 2
    tool_result_content = llm.calls[1]["messages"][-1]["content"][0]["toolResult"]["content"][0]["text"]
    parsed = json.loads(tool_result_content)
    assert parsed["candidates"][0]["concept_id"] == "195967001"


def test_verify_entities_records_failed_attempt_for_empty_response() -> None:
    state = _state()
    with patch("libs.llm_client.factory.create_llm", return_value=_DummyLLM("")):
        result = verify_entities(state)

    # Failed parse still produces a verification_result and increments attempts,
    # so retry loop can terminate deterministically.
    assert result["verification_result"]["is_accurate"] is False
    assert result["verification_result"]["confidence"] == 0.0
    assert result["verification_non_retryable"] is True
    assert result["extraction_attempts"]
    assert "verification_parse_error" in " ".join(result["verification_result"]["issues"])


def test_route_ends_on_non_retryable_verification_error() -> None:
    state = {
        "verification_non_retryable": True,
        "verification_result": {"is_accurate": False, "confidence": 0.0},
        "extraction_attempts": [{"confidence": 0.0}],
        "max_retries": 50,
    }
    assert _route_after_evaluate(state) == "end"
