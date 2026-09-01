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


class _CaptureLLM:
    def __init__(self, text: str, sink: dict[str, str]):
        self._text = text
        self._sink = sink

    def converse(self, **kwargs):
        self._sink["system"] = kwargs.get("system", "")
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
    assert out["has_extraction_changes"] is True


def test_extraction_check_cannot_drop_taught_checkbox(monkeypatch):
    payload = '{"drop":[0]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    letter = (
        "Intractable breast pain not responding to initial conservative "
        "measures - see best practice guidance."
    )
    out = graph.invoke(
        {
            "encounter_text": letter,
            "entities": [
                {
                    "text": "Intractable breast pain",
                    "label": "finding",
                    "assertion": "present",
                    "start": 0,
                    "end": 23,
                    "__source": "form_schema_checkbox",
                }
            ],
        }
    )
    assert len(out["entities"]) == 1
    assert out["entities"][0]["text"] == "Intractable breast pain"


def test_coding_check_cannot_drop_taught_checkbox(monkeypatch):
    payload = '{"drop":[0]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_coding_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "A1. Newly presenting discrete hard lump | Yes [X]",
            "entities": [
                {
                    "text": "Newly presenting discrete hard lump",
                    "label": "finding",
                    "concept_id": "89164003",
                    "__source": "form_schema_checkbox",
                }
            ],
        }
    )
    assert len(out["entities"]) == 1
    assert out["entities"][0]["concept_id"] == "89164003"


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
    assert out["has_coding_issues"] is True


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


def test_extraction_check_drops_referral_suspicion_disorder_inference(monkeypatch):
    payload = '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[]}'
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "Seen in fast track suspected colorectal cancer clinic (XaPyb).",
            "entities": [
                {
                    "text": "Seen in fast track suspected colorectal cancer clinic",
                    "label": "finding",
                    "assertion": "present",
                    "start": 0,
                    "end": 53,
                },
                {
                    "text": "suspected colorectal cancer",
                    "label": "disorder",
                    "assertion": "possible",
                    "start": 19,
                    "end": 47,
                },
            ],
        }
    )
    assert any(e["label"] == "finding" for e in out["entities"])
    assert all(
        not (e["label"] == "disorder" and e.get("assertion") == "possible")
        for e in out["entities"]
    )
    assert any(
        c.get("reason") == "referral_suspicion_disorder_inference"
        for c in out.get("llm_check_changes", [])
    )


def test_extraction_check_applies_relation_updates(monkeypatch):
    payload = (
        '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[],'
        '"correct_relation":[{"index":0,"relations":[{"type":"finding_site","target_idx":1,"target_text":"arm","confidence":0.9}]}],'
        '"add_relation":[{"index":0,"type":"qualifies","target_idx":2,"target_text":"severe","confidence":0.8}]}'
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "severe numbness in arm",
            "entities": [
                {"text": "numbness", "label": "finding", "assertion": "present"},
                {"text": "arm", "label": "body structure", "assertion": "present"},
                {"text": "severe", "label": "qualifier value", "assertion": "present"},
            ],
        }
    )
    relations = out["entities"][0].get("__relations") or []
    assert len(relations) == 2
    assert any(r["type"] == "finding_site" for r in relations)
    assert any(r["type"] == "qualifies" for r in relations)
    assert out["relation_changes"]


def test_extraction_check_prompt_config_is_composed_with_shared_guidelines(monkeypatch):
    payload = '{"drop":[],"correct_assertion":[],"correct_label":[],"add":[]}'
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _CaptureLLM(payload, captured),
    )
    monkeypatch.setattr(
        "libs.prompts.registry.compose_prompt_with_annotation_guidelines",
        lambda name, text: f"{text}\n\n[shared-guidelines:{name}]",
    )
    graph = build_extraction_check_subgraph()
    graph.invoke(
        {
            "encounter_text": "short text",
            "entities": [{"text": "cough", "label": "finding", "assertion": "present"}],
            "prompt_config": {"systemPrompt": "custom extraction check prompt"},
        }
    )
    assert "[shared-guidelines:extraction_check]" in captured.get("system", "")


def test_extraction_check_tolerates_malformed_llm_json(monkeypatch):
    payload = (
        '{ "terms": [ { "text": "Allergies: Shellfish Allergy", '
        '"lookup_term": "allergy to shellfish", "semantic_tag": "situation", '
        '"assertion": "present", "confidence": 0.78, "value": ""'
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_extraction_check_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "Allergies: Shellfish Allergy documented.",
            "entities": [
                {
                    "text": "Shellfish Allergy",
                    "label": "situation",
                    "assertion": "present",
                },
            ],
        }
    )
    assert not out.get("errors")
    assert len(out["entities"]) == 1
    assert out["entities"][0]["text"] == "Shellfish Allergy"
