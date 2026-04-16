from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

import libs.pipeline_graph.subgraphs.relation_linking as relation_linking_mod
from libs.pipeline_graph.subgraphs.relation_linking import build_relation_linking_subgraph


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


def test_relation_linking_adds_relations_and_lookup_term(monkeypatch):
    payload = (
        '{"relations":[{"head_idx":0,"tail_idx":1,"type":"finding_site","confidence":0.94}],'
        '"suppress":[1]}'
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    monkeypatch.setattr(relation_linking_mod, "_MODEL_CONFIDENCE_THRESHOLD", 0.99)
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "no numbness in arm",
            "entities": [
                {"text": "numbness", "label": "finding"},
                {"text": "arm", "label": "body structure"},
            ],
        }
    )
    assert out["entities"][0]["lookup_term"] == "arm numbness"
    assert out["entities"][0]["body_site"] == "arm"
    assert out["entities"][1]["_relation_suppressed"] is True
    assert out["relation_changes"]


def test_relation_linking_model_first_without_llm(monkeypatch):
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM('{"relations":[],"suppress":[]}'),
    )
    monkeypatch.setattr(relation_linking_mod, "_MODEL_CONFIDENCE_THRESHOLD", 0.4)
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "stage 1 lesion in right breast",
            "entities": [
                {"text": "lesion", "label": "finding", "start": 8},
                {"text": "right breast", "label": "body_structure", "start": 19},
            ],
        }
    )
    rels = out["entities"][0].get("__relations") or []
    assert rels
    assert rels[0]["type"] == "finding_site"
    assert rels[0]["target_idx"] == 1


def test_relation_linking_prompt_config_is_composed_with_shared_guidelines(monkeypatch):
    payload = '{"relations":[],"suppress":[]}'
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _CaptureLLM(payload, captured),
    )
    monkeypatch.setattr(
        "libs.prompts.registry.compose_prompt_with_annotation_guidelines",
        lambda name, text: f"{text}\n\n[shared-guidelines:{name}]",
    )
    monkeypatch.setattr(relation_linking_mod, "_MODEL_CONFIDENCE_THRESHOLD", 0.99)
    graph = build_relation_linking_subgraph()
    graph.invoke(
        {
            "encounter_text": "note text",
            "entities": [
                {"text": "numbness", "label": "finding"},
                {"text": "arm", "label": "body structure"},
            ],
            "prompt_config": {"systemPrompt": "custom relation prompt"},
        }
    )
    assert "[shared-guidelines:relation_linking]" in captured.get("system", "")
