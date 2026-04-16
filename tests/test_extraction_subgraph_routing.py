from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

from libs.ner.extractor_contract import ExtractionItem
from libs.pipeline_graph.subgraphs.extraction import extract_entities
from libs.workflow.engine import WorkflowEngine


def test_extract_entities_uses_ner_provider_when_requested(monkeypatch):
    class _Provider:
        def extract_batch(
            self,
            encounter_text,
            chunks,
            requested_model_version=None,
            strict_model_version=False,
        ):
            assert encounter_text == "Patient has asthma."
            assert len(chunks) == 1
            assert requested_model_version is None
            assert strict_model_version is False
            self.model_name = "model-inference"
            self.model_version = "v1"
            return [
                ExtractionItem(
                    sentence_id="s0",
                    text="asthma",
                    span_start=12,
                    span_end=18,
                    semantic_tag="disorder",
                    assertion="present",
                    confidence=0.9,
                    normalized="asthma",
                    source="model",
                    model_name="model-inference",
                    model_version="v1",
                )
            ]

    monkeypatch.setattr(
        "services.coding_worker.app.pipeline.providers.model_provider.ModelExtractorProvider",
        _Provider,
    )

    result = extract_entities(
        {
            "encounter_text": "Patient has asthma.",
            "extraction_method": "ner",
            "sentences": [
                {
                    "sentence_id": "s0",
                    "text": "Patient has asthma.",
                    "start": 0,
                    "end": 19,
                }
            ],
        }
    )
    assert len(result["entities"]) == 1
    assert result["entities"][0]["text"] == "asthma"
    assert result["llm_tokens"]["input_tokens"] == 0


def test_extract_entities_uses_deterministic_lab_fallback_when_ner_empty(monkeypatch):
    class _Provider:
        def extract_batch(
            self,
            encounter_text,
            chunks,
            requested_model_version=None,
            strict_model_version=False,
        ):
            assert encounter_text
            assert chunks
            self.model_name = "model-inference"
            self.model_version = "v1"
            return []

    monkeypatch.setattr(
        "services.coding_worker.app.pipeline.providers.model_provider.ModelExtractorProvider",
        _Provider,
    )

    result = extract_entities(
        {
            "encounter_text": "Neutrophil count (42J..) 5.14 10^9 / L [1.5-7.5]",
            "extraction_method": "ner",
            "sentences": [
                {
                    "sentence_id": "s0",
                    "text": "Neutrophil count (42J..) 5.14 10^9 / L [1.5-7.5]",
                    "start": 0,
                    "end": 49,
                }
            ],
        }
    )
    assert len(result["entities"]) == 1
    ent = result["entities"][0]
    assert ent["text"] == "Neutrophil count"
    assert ent["label"] == "observable_entity"
    assert ent["value"] == "5.14"
    assert ent["unit"] == "10^9/L"
    assert ent["__source"] == "ner_lab_fallback"


def test_extract_entities_raises_when_strict_model_version_error(monkeypatch):
    class _Provider:
        model_name = "model-inference"
        model_version = "v1"

        def extract_batch(
            self,
            encounter_text,
            chunks,
            requested_model_version=None,
            strict_model_version=False,
        ):
            assert requested_model_version == "requested-v2"
            assert strict_model_version is True
            raise RuntimeError(
                "Requested model version requested-v2 but extraction returned model version actual-v3"
            )

    monkeypatch.setattr(
        "services.coding_worker.app.pipeline.providers.model_provider.ModelExtractorProvider",
        _Provider,
    )

    with pytest.raises(RuntimeError, match="Requested model version requested-v2"):
        extract_entities(
            {
                "encounter_text": "Patient has asthma.",
                "extraction_method": "ner",
                "requested_model_version": "requested-v2",
                "strict_model_version": True,
                "sentences": [
                    {
                        "sentence_id": "s0",
                        "text": "Patient has asthma.",
                        "start": 0,
                        "end": 19,
                    }
                ],
            }
        )


# -- _record_to_action node_type inference tests ------------------------------


def _make_record(action_props: dict, ad_props: dict | None):
    """Minimal Neo4j-like record stub for _record_to_action."""

    class _Node(dict):
        pass

    a = _Node(action_props)
    ad = _Node(ad_props) if ad_props is not None else None
    return {"a": a, "ad": ad}


def test_record_to_action_condition_explicit_node_type():
    """Action node with nodeType stored explicitly is respected."""
    record = _make_record(
        {"id": "act-1", "nodeType": "condition", "sequence": 5},
        {"subgraphId": "condition", "dynamicValues": None},
    )
    action = WorkflowEngine._record_to_action(record)
    assert action.node_type == "condition"
    assert action.subgraph_id == "condition"


def test_record_to_action_condition_inferred_from_subgraph_id():
    """Stale Action node without nodeType gets node_type inferred from subgraph_id.

    This is the regression fix for 'Unknown subgraph: condition' when a plan
    was seeded before nodeType was stored on the Action node.
    """
    record = _make_record(
        {"id": "act-extraction-route", "sequence": 5},
        {"subgraphId": "condition", "dynamicValues": None},
    )
    action = WorkflowEngine._record_to_action(record)
    assert action.node_type == "condition", (
        "node_type should be inferred as 'condition' from subgraph_id "
        "when the Action node lacks a nodeType property"
    )


def test_record_to_action_trigger_inferred_from_subgraph_id():
    """Stale trigger Action node without nodeType gets node_type 'trigger'."""
    record = _make_record(
        {"id": "act-trigger", "sequence": 0},
        {"subgraphId": "trigger", "dynamicValues": None},
    )
    action = WorkflowEngine._record_to_action(record)
    assert action.node_type == "trigger"


def test_record_to_action_ordinary_action_defaults_to_action():
    """Regular action without nodeType defaults to 'action'."""
    record = _make_record(
        {"id": "act-extract", "sequence": 1},
        {"subgraphId": "extraction", "dynamicValues": None},
    )
    action = WorkflowEngine._record_to_action(record)
    assert action.node_type == "action"
    assert action.subgraph_id == "extraction"
