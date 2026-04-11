"""Extraction subgraph wrapping sentence splitter and extractor registry.

Prompt resolution order:
1. ``prompt_config`` dict in state (populated from Neo4j by the parent graph)
2. ``libs.prompts.registry.get_prompt("extraction", 1)`` (Neo4j → hardcoded)
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.nlp.sentence_splitter import (
    SentenceChunk,
    SentenceSplitter,
    filter_header_sentences,
    is_non_evidence_line,
)

logger = logging.getLogger(__name__)


class ExtractionState(TypedDict, total=False):
    encounter_id: str
    encounter_text: str
    extraction_method: str
    prompt_config: dict[str, Any]
    sentences: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    errors: list[str]


def _items_to_dicts(items: list) -> list[dict[str, Any]]:
    return [
        {
            "text": item.text,
            "label": item.semantic_tag,
            "start": item.span_start,
            "end": item.span_end,
            "assertion": item.assertion or "present",
            "confidence": item.confidence,
            "normalized": (
                item.normalized
                if item.normalized and item.normalized != item.text
                else None
            ),
            "value": item.numeric_value or None,
            "unit": item.unit or None,
            "reference_range": item.reference_range or None,
            "__sentence_id": item.sentence_id,
            "__source": item.source,
            "__model_name": item.model_name,
            "__model_version": item.model_version,
            "__contract_version": item.contract_version,
            "__source_meta": item.source_meta,
            "__relations": item.relations,
        }
        for item in items
    ]


def _hydrate_encounter_text_if_missing(state: ExtractionState) -> str:
    text = str(state.get("encounter_text") or "").strip()
    if text:
        return text

    encounter_id = str(state.get("encounter_id") or "").strip()
    if not encounter_id:
        return ""

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (e:Encounter {id: $encounter_id}) "
            "RETURN coalesce(e.text, '') AS text",
            encounter_id=encounter_id,
        )
    finally:
        client.close()

    hydrated = str((rows or [{}])[0].get("text") or "").strip()
    if hydrated:
        logger.warning(
            "Encounter text missing in state for encounter_id=%s; "
            "hydrated from Neo4j in extraction step",
            encounter_id,
        )
    else:
        logger.warning(
            "Encounter text missing in state and Neo4j for encounter_id=%s",
            encounter_id,
        )
    return hydrated


def split_sentences(state: ExtractionState) -> dict[str, Any]:
    text = _hydrate_encounter_text_if_missing(state)
    splitter = SentenceSplitter()
    chunks = splitter.split(text)
    chunks = filter_header_sentences(chunks)
    chunks = [chunk for chunk in chunks if not is_non_evidence_line(chunk.text)]
    return {"encounter_text": text, "sentences": [asdict(c) for c in chunks]}


def _resolve_system_prompt(state: ExtractionState) -> str:
    """Get the extraction system prompt from state config or the registry."""
    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return cfg["systemPrompt"]
    from libs.prompts.registry import get_prompt
    return get_prompt("extraction", version=1)


def extract_entities(state: ExtractionState) -> dict[str, Any]:
    encounter_text = state.get("encounter_text") or ""
    raw_sentences = state.get("sentences") or []
    extraction_method = str(state.get("extraction_method") or "llm").lower()
    try:
        chunks = [
            SentenceChunk(
                sentence_id=s.get("sentence_id", ""),
                text=s.get("text", ""),
                start=int(s.get("start", 0)),
                end=int(s.get("end", 0)),
            )
            for s in raw_sentences
        ]
        if extraction_method == "ner":
            from services.coding_worker.app.pipeline.providers.model_provider import (
                ModelExtractorProvider,
            )
            extractor = ModelExtractorProvider()
            items = extractor.extract_batch(encounter_text, chunks)
            return {
                "entities": _items_to_dicts(items),
                "llm_tokens": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "cost_usd": 0.0,
                },
            }

        from libs.pipeline_graph.subgraphs._extractor import build_extractor

        cfg = state.get("prompt_config") or {}
        system_prompt = _resolve_system_prompt(state)

        # Pass output schema + examples so the extractor can assemble the full prompt
        output_schema_json: str | None = cfg.get("outputSchema") or None
        try:
            max_few_shot = int(cfg.get("maxFewShot") or 20)
        except (TypeError, ValueError):
            max_few_shot = 20
        few_shot_raw = cfg.get("fewShotExamples")
        few_shot_examples: list[dict] | None = None
        if few_shot_raw:
            import json as _json
            try:
                few_shot_examples = (
                    _json.loads(few_shot_raw)
                    if isinstance(few_shot_raw, str)
                    else few_shot_raw
                )
            except Exception:
                few_shot_examples = None

        try:
            prompt_version = int(cfg.get("version") or 1)
        except (TypeError, ValueError):
            prompt_version = 1

        extractor = build_extractor(
            system_prompt=system_prompt,
            output_schema_json=output_schema_json,
            few_shot_examples=few_shot_examples,
            max_few_shot=max_few_shot,
            prompt_name=str(cfg.get("name") or "extraction"),
            prompt_version=prompt_version,
        )
        items, llm_tokens = extractor.extract_batch_with_usage(encounter_text, chunks)
        return {"entities": _items_to_dicts(items), "llm_tokens": llm_tokens}
    except ImportError as e:
        logger.warning("Extractor unavailable: %s", e)
        return {"entities": [], "errors": [str(e)]}
    except Exception as e:
        logger.exception("Entity extraction failed")
        return {"entities": [], "errors": [str(e)]}


def merge_results(state: ExtractionState) -> dict[str, Any]:
    return {
        "entities": state.get("entities", []),
        "errors": state.get("errors", []),
    }


def build_extraction_subgraph() -> CompiledStateGraph:
    g = StateGraph(ExtractionState)
    g.add_node("split_sentences", split_sentences)
    g.add_node("extract_entities", extract_entities)
    g.add_node("merge_results", merge_results)
    g.add_edge(START, "split_sentences")
    g.add_edge("split_sentences", "extract_entities")
    g.add_edge("extract_entities", "merge_results")
    g.add_edge("merge_results", END)
    return g.compile()
