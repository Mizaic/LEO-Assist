"""VT-LEO-AI-200 -- AI first-pass Haiku extractor.

Cases:
  TC-001: extractor falls back to original entities on Haiku failure.
  TC-002: extractor uses top-K nearest gold few-shot exemplars.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from services.api.app.services.candidate_ai_first_pass import _extractor
from services.api.app.services.candidate_ai_first_pass._extractor import (
    ai_extract_entities,
)


def _candidate(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_id": "cand-1",
        "text": text,
        "entities_json": json.dumps(entities),
    }


def _prompt_loader() -> tuple[str, dict[str, Any]]:
    return "managed extraction prompt", {"type": "array", "items": {"type": "object"}}


def test_extractor_loads_managed_prompt_bundle(monkeypatch):
    schema = {"type": "array", "items": {"type": "object"}}
    monkeypatch.setattr(
        _extractor,
        "get_prompt_config",
        lambda *_args, **_kwargs: {
            "systemPrompt": "managed",
            "outputSchema": json.dumps(schema),
            "fewShotExamples": [],
        },
    )
    monkeypatch.setattr(
        _extractor,
        "_assemble_managed_prompt",
        lambda **kwargs: f"assembled:{kwargs['instructions']}",
    )

    system, loaded_schema = _extractor._load_registry_prompt()

    assert system == "assembled:managed"
    assert loaded_schema == schema


def test_VT_194_TC_001_extractor_falls_back_on_llm_failure():
    cand = _candidate(
        "Patient denies chest pain. HbA1c 58.",
        [{"text": "chest pain", "label": "finding", "assertion": "absent"}],
    )

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    selector = MagicMock()
    selector.select.return_value = []

    result = ai_extract_entities(
        candidate=cand,
        selector=selector,
        k=5,
        tier="small",
        call_llm=_raise,
        prompt_loader=_prompt_loader,
    )

    assert result.fallback_used is True
    assert result.extractor_error and result.extractor_error.startswith("llm_error:")
    assert result.entity_count == 1
    assert result.entities[0].text == "chest pain"
    assert result.entities[0].assertion == "absent"


def test_VT_194_TC_002_extractor_requests_top_k_few_shot_exemplars():
    cand = _candidate(
        "FBC: Hb 12 g/dL, plt 250 10^9/L.",
        [{"text": "FBC", "label": "procedure"}],
    )

    captured: dict[str, Any] = {}

    def _stub_llm(system, user_msg, *, tier="small", **kwargs):
        captured["system"] = system
        captured["user_msg"] = user_msg
        captured["tier"] = tier
        captured["schema"] = kwargs.get("structured_schema")
        return (
            json.dumps(
                [
                    {"text": "FBC", "label": "procedure"},
                    {"text": "Hb", "label": "observable entity"},
                ]
            ),
            "haiku-test",
        )

    selector = MagicMock()
    selector.select.return_value = [
        {
            "category": "gold:labs",
            "description": "Hb result",
            "input": "Hb 12 g/dL",
            "output": [{"text": "Hb", "label": "observable entity"}],
        }
    ]

    result = ai_extract_entities(
        candidate=cand,
        selector=selector,
        k=5,
        tier="small",
        call_llm=_stub_llm,
        prompt_loader=_prompt_loader,
    )

    selector.select.assert_called_once()
    args, kwargs = selector.select.call_args
    assert args[0] == cand["text"] or kwargs.get("query_text") == cand["text"]
    if len(args) > 1:
        assert args[1] == 5
    else:
        assert kwargs.get("k") == 5
    assert result.fallback_used is False
    assert result.entity_count == 2
    assert captured["system"] == "managed extraction prompt"
    assert captured["schema"]["type"] == "array"
    assert "Hb 12 g/dL" in captured["user_msg"]
    assert captured["tier"] == "small"


def test_extractor_falls_back_on_unparseable_llm_output():
    cand = _candidate(
        "Some text",
        [{"text": "diabetes", "label": "disorder"}],
    )

    def _stub_llm(_s, _u, *, tier="small", **_kw):
        return ("not valid json at all", "haiku-test")

    result = ai_extract_entities(
        candidate=cand,
        selector=None,
        k=5,
        tier="small",
        call_llm=_stub_llm,
        prompt_loader=_prompt_loader,
    )

    assert result.fallback_used is True
    assert result.extractor_error == "parse_error"
    assert result.entity_count == 1
    assert result.entities[0].text == "diabetes"
