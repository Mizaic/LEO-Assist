from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

import libs.pipeline_graph.subgraphs.relation_linking as relation_linking_mod
from libs.pipeline_graph.subgraphs.relation_linking import (
    _model_predict_relations,
    _pick_relation_type,
    build_relation_linking_subgraph,
)
from libs.relations.policy import is_relation_allowed


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


def test_policy_rejects_finding_finding_qualifies():
    allowed, _ = is_relation_allowed(
        source_label="finding",
        target_label="finding",
        relation_type="qualifies",
    )
    assert not allowed, "finding->finding via qualifies must be rejected by policy"


def test_policy_allows_qualifier_value_qualifies_finding():
    allowed, severity = is_relation_allowed(
        source_label="qualifier_value",
        target_label="finding",
        relation_type="qualifies",
    )
    assert allowed
    assert severity == "warning"


def test_pick_relation_type_skips_without_prior_and_no_offsets():
    allowed_types = ["associated_finding", "qualifies"]
    rel, conf = _pick_relation_type(
        {"text": "jaundice", "label": "finding"},
        {"text": "weight loss", "label": "finding"},
        {},
        allowed_types,
    )
    assert rel is None, "no pair_prior and no offsets must produce no relation"


def test_pick_relation_type_skips_when_entities_too_far_apart():
    rel, _ = _pick_relation_type(
        {"text": "jaundice", "label": "finding", "start": 0},
        {"text": "weight loss", "label": "finding", "start": 900},
        {},
        ["finding_site"],
    )
    assert rel is None


def test_pick_relation_type_allows_finding_site_when_close():
    rel, conf = _pick_relation_type(
        {"text": "pain", "label": "finding", "start": 10},
        {"text": "abdomen", "label": "body_structure", "start": 20},
        {},
        ["finding_site"],
    )
    assert rel == "finding_site"
    assert conf > 0.62


def test_model_predict_relations_no_cartesian_product():
    """Ten co-occurring findings must not produce a wall of qualifies/associated_finding."""
    findings = [
        {"text": f"finding_{i}", "label": "finding"} for i in range(10)
    ]
    result = _model_predict_relations(findings)
    assert result["relations"] == [], (
        "Without pair_priors and no offsets, model must produce zero relations "
        f"for finding-only entities; got {len(result['relations'])}"
    )


def test_apply_relation_linking_rejects_finding_finding_qualifies(monkeypatch):
    """LLM returns a finding->finding qualifies; the apply step must discard it."""
    llm_payload = (
        '{"relations":[{"head_idx":0,"tail_idx":1,"type":"qualifies","confidence":0.9}],'
        '"suppress":[]}'
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(llm_payload),
    )
    monkeypatch.setattr(relation_linking_mod, "_MODEL_CONFIDENCE_THRESHOLD", 0.99)
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "jaundice and weight loss",
            "entities": [
                {"text": "jaundice", "label": "finding"},
                {"text": "weight loss", "label": "finding"},
            ],
        }
    )
    for entity in out["entities"]:
        rels = entity.get("__relations") or []
        for rel in rels:
            assert rel["type"] != "qualifies", (
                "finding->finding qualifies must be rejected by apply guard"
            )


def test_relation_linking_tolerates_malformed_llm_json(monkeypatch):
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM("{bad json: trailing, comma,}"),
    )
    monkeypatch.setattr(relation_linking_mod, "_MODEL_CONFIDENCE_THRESHOLD", 0.99)
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "no numbness in arm",
            "entities": [
                # start offsets let the proximity predictor link these two.
                {"text": "numbness", "label": "finding", "start": 3},
                {"text": "arm", "label": "body structure", "start": 15},
            ],
        }
    )
    assert not out.get("errors")
    assert out["entities"][0].get("lookup_term") == "arm numbness"


def test_judge_confirms_snomed_candidate(monkeypatch):
    payload = (
        '{"confirmed":[{"head_idx":0,"tail_idx":1,"type":"finding_site",'
        '"confidence":0.94}],"rejected":[],"additional":[],"suppress":[1]}'
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "numbness in arm",
            "entities": [
                {
                    "text": "numbness",
                    "label": "finding",
                    "__snomed_relations": [
                        {
                            "type": "finding_site",
                            "target_idx": 1,
                            "target_text": "arm",
                            "confidence": 0.9,
                            "source": "snomed",
                        }
                    ],
                },
                {"text": "arm", "label": "body structure", "inferred": True},
            ],
        }
    )
    rels = out["entities"][0].get("__relations") or []
    assert rels[0]["type"] == "finding_site"
    assert rels[0]["extraction_method"] == "snomed+llm"
    assert out["entities"][0]["lookup_term"] == "arm numbness"


def test_judge_failure_keeps_snomed_candidates(monkeypatch):
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM("{bad json"),
    )
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "numbness in arm",
            "entities": [
                {
                    "text": "numbness",
                    "label": "finding",
                    "__snomed_relations": [
                        {
                            "type": "finding_site",
                            "target_idx": 1,
                            "target_text": "arm",
                            "confidence": 0.9,
                            "source": "snomed",
                        }
                    ],
                },
                {"text": "arm", "label": "body structure"},
            ],
        }
    )
    rels = out["entities"][0].get("__relations") or []
    assert rels[0]["type"] == "finding_site"
    assert rels[0]["extraction_method"] == "snomed"


def test_judge_can_reject_all_snomed_candidates(monkeypatch):
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(
            '{"confirmed":[],"rejected":[{"head_idx":0,"tail_idx":1,'
            '"reason":"not in this note"}],"additional":[],"suppress":[]}'
        ),
    )
    graph = build_relation_linking_subgraph()
    out = graph.invoke(
        {
            "encounter_text": "unrelated note",
            "entities": [
                {
                    "text": "jaundice",
                    "label": "finding",
                    "__snomed_relations": [
                        {
                            "type": "finding_site",
                            "target_idx": 1,
                            "target_text": "liver",
                            "confidence": 0.9,
                            "source": "snomed",
                        }
                    ],
                },
                {"text": "liver", "label": "body_structure", "inferred": True},
            ],
        }
    )
    assert not (out["entities"][0].get("__relations") or [])
