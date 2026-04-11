from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

from libs.pipeline_graph.subgraphs.llm_check import (
    build_coding_check_subgraph,
    build_extraction_check_subgraph,
)


class _Resp:
    def __init__(self, text: str):
        self.text = text


class _LLM:
    def __init__(self, text: str):
        self._text = text

    def converse(self, **kwargs):
        assert "system" in kwargs
        assert "messages" in kwargs
        return _Resp(self._text)


def test_extraction_check_applies_drop_and_corrections(monkeypatch):
    payload = (
        '{"drop":[1],'
        '"correct_assertion":[{"index":0,"assertion":"historical"}],'
        '"correct_label":[{"index":0,"label":"finding"}],'
        '"add":[{"text":"iron deficiency anaemia","label":"disorder","assertion":"present","lookup_term":"iron deficiency anaemia"}]}'
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.llm_check.create_llm",
        lambda tier="small": _LLM(payload),
        raising=False,
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )

    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "History of diabetes. Discussed template. Iron deficiency anaemia noted.",
            "entities": [
                {"text": "diabetes", "label": "disorder", "assertion": "present"},
                {"text": "template", "label": "finding", "assertion": "present"},
            ],
        }
    )
    assert len(out["entities"]) == 2
    assert out["entities"][0]["assertion"] == "historical"
    assert out["entities"][0]["label"] == "finding"
    assert out["entities"][1]["_llm_check_source"] == "llm_added"


def test_coding_check_applies_drop_and_force_review(monkeypatch):
    payload = '{"drop":[1],"force_review":[0]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_coding_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "Possible urgent referral discussed.",
            "entities": [
                {"text": "urgent referral", "concept_id": "3457005"},
                {"text": "template noise", "concept_id": "123"},
            ],
        }
    )
    assert len(out["entities"]) == 1
    assert out["entities"][0]["_tier_override"] == 2
    assert (
        out["entities"][0]["_tier_override_reason"] == "llm_coding_check_force_review"
    )


def test_extraction_check_keeps_referral_procedure_as_present(monkeypatch):
    payload = '{"correct_assertion":[{"index":0,"assertion":"possible"}]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "Fast track referral for suspected breast cancer arranged.",
            "entities": [
                {
                    "text": "Fast track referral for suspected breast cancer",
                    "label": "procedure",
                    "assertion": "present",
                },
            ],
        }
    )
    assert out["entities"][0]["assertion"] == "present"
    assert out["entities"][0]["_assertion_guard"] == "referral_procedure"


def test_extraction_check_suppresses_medication_instruction_indication(monkeypatch):
    payload = '{"add":[{"text":"low mood","label":"finding","assertion":"present"}]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "Fluoxetine 20mg capsules - take two daily for low mood",
            "entities": [
                {
                    "text": "Fluoxetine 20mg capsules",
                    "label": "substance",
                    "assertion": "present",
                },
            ],
        }
    )
    assert any(e["text"] == "Fluoxetine 20mg capsules" for e in out["entities"])
    assert all(e["text"] != "low mood" for e in out["entities"])
