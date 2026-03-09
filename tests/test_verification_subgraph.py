from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.verification import _route_after_evaluate, verify_entities


class _DummyResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _DummyLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def converse(self, **_: object) -> _DummyResponse:
        return _DummyResponse(self._text)


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
    assert result["extraction_attempts"]


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
