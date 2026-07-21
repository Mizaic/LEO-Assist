"""Extraction subgraph wrapping sentence splitter and extractor registry.

Atlas trace:
  DO: DO-728930A1
  Also implements: DO-416BA91D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

Prompt resolution order:
1. ``prompt_config`` dict in state (populated from Neo4j by the parent graph)
2. ``libs.prompts.registry.get_prompt("extraction", 1)`` (Neo4j → hardcoded)
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.ner.schema_mapper import normalise_label
from libs.nlp.sentence_splitter import (
    SentenceChunk,
    SentenceSplitter,
    filter_header_sentences,
    is_non_evidence_line,
)

logger = logging.getLogger(__name__)

_LAB_VALUE_RE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z\s\-']{2,}?)\s*(?:\([^)]*\))?\s*"
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?)\s*"
    r"(?P<unit>(?:10\^\d+\s*/\s*[A-Za-z]+|[A-Za-z%]+(?:\s*/\s*[A-Za-z]+)*))",
    re.IGNORECASE,
)
_LAB_NAME_HINTS = (
    "count",
    "concentration",
    "haematocrit",
    "hematocrit",
    "haemoglobin",
    "hemoglobin",
    "cell volume",
    "cell haemoglobin",
    "cell hemoglobin",
    "platelet",
    "neutrophil",
    "lymphocyte",
    "monocyte",
    "eosinophil",
    "basophil",
    "blood cell",
    "white blood",
    "red blood",
)


class ExtractionState(TypedDict, total=False):
    encounter_id: str
    encounter_text: str
    source_node_type: str
    source_node_id: str
    source_text_property: str
    extraction_method: str
    model_mode: str
    requested_model_version: str
    strict_model_version: bool
    prompt_config: dict[str, Any]
    sentences: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    extraction_model_name: str
    extraction_model_version: str
    extraction_model_requested_version: str
    extraction_model_version_mismatch: bool
    extraction_route: str
    text_segmentation_mode: str
    chunk_ids: list[str]
    document_reference_id: str
    errors: list[str]


_VALID_MODEL_MODES = {"llm", "ner", "auto"}
_NER_ENABLED_ENV = "MODEL_MODE_NER_ENABLED"


def _ner_backend_enabled() -> bool:
    """True when the NER inference backend is feature-gated on.

    Reads MODEL_MODE_NER_ENABLED first (explicit, per-environment opt-in
    while the NER model is being trained). Falls back to the existing
    CODING_MODEL_PROVIDER_ENABLED so deployments that already enable the
    backend do not regress.
    """
    import os

    primary = os.getenv(_NER_ENABLED_ENV, "").strip().lower()
    if primary in {"1", "true", "yes", "on"}:
        return True
    if primary in {"0", "false", "no", "off"}:
        return False
    secondary = os.getenv("CODING_MODEL_PROVIDER_ENABLED", "").strip().lower()
    return secondary in {"1", "true", "yes", "on"}


def _resolve_model_mode(state: dict[str, Any]) -> str:
    """Resolve the active model mode for this extraction step.

    Precedence (highest first):
      1. state.requested_model_mode (per-request override; promoted from the
         pub/sub payload `context.model_mode` by the workflow engine so that
         action-level config cannot clobber the caller's intent).
      2. state.model_mode (action-level config; defaults like
         ad-extraction-auto pin "auto" here).
      3. state.extraction_method (legacy action config: 'llm' or 'ner').
      4. extraction_model_mode feature flag (process-wide default).

    Returns one of: ``llm``, ``ner``, ``auto``.
    """
    for key in ("requested_model_mode", "model_mode"):
        raw = str(state.get(key) or "").strip().lower()
        if raw in _VALID_MODEL_MODES:
            return raw
    legacy = str(state.get("extraction_method") or "").strip().lower()
    if legacy in {"llm", "ner"}:
        return legacy
    if legacy == "auto":
        return "auto"
    try:
        from libs.feature_flags import EXTRACTION_MODEL_MODE, resolve

        return resolve(EXTRACTION_MODEL_MODE.name)
    except Exception:
        return "llm"


_SOURCE_NODE_CONFIG = {
    "Encounter": {
        "graph": "patient",
        "id_property": "id",
        "text_properties": ("text",),
    },
    "Document": {
        "graph": "patient",
        "id_property": "id",
        "text_properties": ("text", "content", "body"),
    },
    "DocumentReference": {
        "graph": "patient",
        "id_property": "id",
        "text_properties": ("text", "content", "body", "description"),
    },
    "Chunk": {
        "graph": "patient",
        "id_property": "id",
        "text_properties": ("text",),
    },
    "Communication": {
        "graph": "patient",
        "id_property": "id",
        "text_properties": ("note",),
    },
    "ExtractionScenario": {
        "graph": "knowledge",
        "id_property": "case_id",
        "text_properties": ("markdown_body", "source_template_markdown"),
    },
    "TrainingCandidate": {
        "graph": "knowledge",
        "id_property": "id",
        "text_properties": ("text", "source_text"),
    },
}


def _normalise_item_label(semantic_tag: str) -> str:
    """Return the canonical underscore-form label for post-processing.

    ExtractionItem.semantic_tag uses SNOMED space form (e.g. 'observable entity')
    when it comes from the NER model path (via LABEL_TO_SNOMED_TAG). All
    post-processing layer comparisons use the underscore form
    ('observable_entity'). Normalising here ensures Layers 3c, 5, 6, and 7c
    operate correctly on NER-sourced entities without each layer having to
    handle both forms.
    """
    canonical = normalise_label(semantic_tag)
    if canonical:
        return canonical
    return semantic_tag.lower().replace(" ", "_").replace("/", "_")


def _items_to_dicts(items: list) -> list[dict[str, Any]]:
    return [
        {
            "text": item.text,
            "label": _normalise_item_label(item.semantic_tag),
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

    source_text = _hydrate_source_node_text(state)
    if source_text:
        return source_text

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


def _hydrate_source_node_text(state: ExtractionState) -> str:
    source_type = str(state.get("source_node_type") or "").strip()
    source_id = str(state.get("source_node_id") or "").strip()
    if not source_type or not source_id:
        return ""
    config = _SOURCE_NODE_CONFIG.get(source_type)
    if not config:
        logger.warning("Unsupported extraction source_node_type=%s", source_type)
        return ""

    text_properties = _source_text_properties(state, config)
    client = _source_graph_client(str(config["graph"]))
    try:
        rows = client.run(
            _source_text_query(
                source_type,
                str(config["id_property"]),
                text_properties,
            ),
            source_id=source_id,
        )
    finally:
        client.close()

    hydrated = str((rows or [{}])[0].get("text") or "").strip()
    if hydrated:
        logger.info(
            "Hydrated extraction text from %s(%s) properties=%s",
            source_type,
            source_id,
            ",".join(text_properties),
        )
    else:
        logger.warning(
            "Extraction source text missing for %s(%s) properties=%s",
            source_type,
            source_id,
            ",".join(text_properties),
        )
    return hydrated


def _source_text_properties(
    state: ExtractionState,
    config: dict[str, Any],
) -> tuple[str, ...]:
    allowed = tuple(str(item) for item in config["text_properties"])
    requested = str(state.get("source_text_property") or "").strip()
    if requested and requested in allowed:
        return (requested,)
    if requested:
        logger.warning(
            "Ignoring unsupported source_text_property=%s for source_node_type",
            requested,
        )
    return allowed


def _source_graph_client(graph: str):
    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

    if graph == "knowledge":
        return KnowledgeGraphClient()
    return PatientGraphClient()


def _source_text_query(
    label: str,
    id_property: str,
    text_properties: tuple[str, ...],
) -> str:
    coalesce_args = ", ".join(f"n.{prop}" for prop in text_properties)
    return (
        f"MATCH (n:{label} {{{id_property}: $source_id}}) "
        f"RETURN coalesce({coalesce_args}, '') AS text"
    )


def _extract_lab_fallback_entities(
    encounter_text: str,
    chunks: list[SentenceChunk],
) -> list[dict[str, Any]]:
    fallback: list[dict[str, Any]] = []
    for chunk in chunks:
        text = chunk.text or ""
        for m in _LAB_VALUE_RE.finditer(text):
            name = " ".join((m.group("name") or "").split()).strip()
            lower_name = name.lower()
            if not name or not any(h in lower_name for h in _LAB_NAME_HINTS):
                continue
            value = " ".join((m.group("value") or "").split()).strip()
            unit = re.sub(r"\s*/\s*", "/", (m.group("unit") or "").strip())
            start = chunk.start + m.start("name")
            end = chunk.start + m.end("name")
            fallback.append(
                {
                    "text": name,
                    "label": "observable_entity",
                    "start": start,
                    "end": end,
                    "assertion": "present",
                    "confidence": 0.7,
                    "normalized": None,
                    "value": value or None,
                    "unit": unit or None,
                    "reference_range": None,
                    "__sentence_id": chunk.sentence_id,
                    "__source": "ner_lab_fallback",
                    "__model_name": "deterministic-fallback",
                    "__model_version": "v1",
                    "__contract_version": "",
                    "__source_meta": {},
                    "__relations": [],
                }
            )
    return fallback


def load_document_chunks(state: ExtractionState) -> dict[str, Any]:
    """Use pre-loaded HCCP :Chunk rows as extraction units (no SentenceSplitter)."""
    from libs.pipeline.document_chunk_loader import (
        CHUNK_TEXT_SEPARATOR,
        DOCUMENT_CHUNKS_MODE,
        chunk_ids_from_state,
        load_document_chunks_from_neo4j,
    )

    raw_sentences = state.get("sentences") or []
    if raw_sentences:
        encounter_text = state.get("encounter_text") or ""
        if not encounter_text:
            encounter_text = CHUNK_TEXT_SEPARATOR.join(
                str(s.get("text") or "") for s in raw_sentences if s.get("text")
            )
        return {
            "encounter_text": encounter_text,
            "sentences": raw_sentences,
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        }

    chunk_ids = chunk_ids_from_state(state)
    if not chunk_ids:
        return {
            "encounter_text": "",
            "sentences": [],
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "errors": ["document_chunks mode requires chunk_ids or pre-loaded sentences"],
        }

    from libs.neo4j_client.client import PatientGraphClient

    loaded = load_document_chunks_from_neo4j(PatientGraphClient(), chunk_ids)
    if loaded.get("sentences"):
        return {
            "encounter_text": loaded.get("encounter_text") or "",
            "sentences": loaded.get("sentences") or [],
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "errors": list(state.get("errors") or []) + list(loaded.get("errors") or []),
        }
    return {
        "encounter_text": "",
        "sentences": [],
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "errors": list(state.get("errors") or []) + list(loaded.get("errors") or []),
    }


def load_communication_thread(state: ExtractionState) -> dict[str, Any]:
    """Use pre-loaded A&G thread sentences (no SentenceSplitter)."""
    from libs.pipeline.communication_thread_loader import COMMUNICATION_THREAD_MODE
    from libs.pipeline.document_chunk_loader import (
        CHUNK_TEXT_SEPARATOR,
        chunk_ids_from_state,
    )

    raw_sentences = state.get("sentences") or []
    if raw_sentences:
        encounter_text = state.get("encounter_text") or ""
        if not encounter_text:
            encounter_text = CHUNK_TEXT_SEPARATOR.join(
                str(s.get("text") or "") for s in raw_sentences if s.get("text")
            )
        return {
            "encounter_text": encounter_text,
            "sentences": raw_sentences,
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        }

    cr_id = str(state.get("communication_request_id") or "").strip()
    if not cr_id:
        return {
            "encounter_text": "",
            "sentences": [],
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
            "errors": [
                "communication_thread mode requires communication_request_id "
                "or pre-loaded sentences"
            ],
        }

    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline.communication_thread_loader import (
        load_communication_thread_from_neo4j,
    )

    loaded = load_communication_thread_from_neo4j(
        PatientGraphClient(),
        cr_id,
        chunk_ids=chunk_ids_from_state(state) or None,
    )
    if loaded.get("sentences"):
        return {
            "encounter_text": loaded.get("encounter_text") or "",
            "sentences": loaded.get("sentences") or [],
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
            "errors": list(state.get("errors") or []) + list(loaded.get("errors") or []),
        }
    return {
        "encounter_text": "",
        "sentences": [],
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "errors": list(state.get("errors") or []) + list(loaded.get("errors") or []),
    }


def resolve_text_units(state: ExtractionState) -> dict[str, Any]:
    from libs.pipeline.communication_thread_loader import is_communication_thread_mode
    from libs.pipeline.document_chunk_loader import is_document_chunks_mode

    if is_document_chunks_mode(state):
        return load_document_chunks(state)
    if is_communication_thread_mode(state):
        return load_communication_thread(state)
    return split_sentences(state)


def split_sentences(state: ExtractionState) -> dict[str, Any]:
    from libs.pipeline.llm_clinical_input import deidentify_encounter_text

    text = deidentify_encounter_text(_hydrate_encounter_text_if_missing(state))
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


def _run_ner_extraction(
    encounter_text: str,
    chunks: list[SentenceChunk],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Invoke the NER extractor and shape its output for state merge.

    Caller decides what to do on empty output -- this function never falls
    back to the LLM. Returns the same dict shape as the LLM branch with an
    extra ``extraction_route="ner"`` annotation.
    """
    from services.coding_worker.app.pipeline.providers.model_provider import (
        ModelExtractorProvider,
    )

    extractor = ModelExtractorProvider()
    requested_model_version = str(state.get("requested_model_version") or "").strip()
    strict_model_version = bool(state.get("strict_model_version", False))
    items = extractor.extract_batch(
        encounter_text,
        chunks,
        requested_model_version=requested_model_version or None,
        strict_model_version=strict_model_version,
    )
    actual_model_version = str(extractor.model_version or "").strip()
    mismatch = bool(
        requested_model_version
        and actual_model_version
        and requested_model_version != actual_model_version
    )
    entities = _items_to_dicts(items)
    return {
        "entities": entities,
        "extraction_model_name": str(extractor.model_name or ""),
        "extraction_model_version": actual_model_version,
        "extraction_model_requested_version": requested_model_version,
        "extraction_model_version_mismatch": mismatch,
        "extraction_route": "ner",
        "llm_tokens": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cost_usd": 0.0,
        },
    }


def _run_llm_extraction(
    encounter_text: str,
    chunks: list[SentenceChunk],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Invoke the LLM extractor and shape its output for state merge."""
    from libs.pipeline_graph.subgraphs._extractor import build_extractor

    cfg = state.get("prompt_config") or {}
    system_prompt = _resolve_system_prompt(state)

    output_schema_json: str | None = cfg.get("outputSchema") or None
    try:
        max_few_shot = int(cfg.get("maxFewShot") or 20)
    except (TypeError, ValueError):
        max_few_shot = 20
    import json as _json

    few_shot_raw = cfg.get("fewShotExamples")
    few_shot_examples: list[dict] | None = None
    if few_shot_raw:
        try:
            few_shot_examples = (
                _json.loads(few_shot_raw)
                if isinstance(few_shot_raw, str)
                else few_shot_raw
            )
        except Exception:
            few_shot_examples = None

    # When prompt_config is absent from state (e.g. referral durable pipeline
    # which bypasses WorkflowEngine), fall back to loading examples from the
    # registry so both encounter and referral paths get the same few-shot pool.
    if few_shot_examples is None and not cfg:
        try:
            from libs.prompts.registry import get_prompt_config

            fallback_cfg = get_prompt_config("extraction", version=1)
            fallback_raw = fallback_cfg.get("fewShotExamples")
            if fallback_raw:
                few_shot_examples = (
                    _json.loads(fallback_raw)
                    if isinstance(fallback_raw, str)
                    else fallback_raw
                )
        except Exception:
            pass

    try:
        prompt_version = int(cfg.get("version") or 1)
    except (TypeError, ValueError):
        prompt_version = 1

    import os

    tier = str(state.get("model_tier") or os.getenv("PIPELINE_MODEL_TIER") or "small")
    if tier not in {"small", "big", "max"}:
        tier = "small"

    extractor = build_extractor(
        system_prompt=system_prompt,
        tier=tier,
        output_schema_json=output_schema_json,
        few_shot_examples=few_shot_examples,
        max_few_shot=max_few_shot,
        prompt_name=str(cfg.get("name") or "extraction"),
        prompt_version=prompt_version,
    )
    items, llm_tokens = extractor.extract_batch_with_usage(encounter_text, chunks)
    return {
        "entities": _items_to_dicts(items),
        "llm_tokens": llm_tokens,
        "extraction_route": "llm",
    }


def _enrich_with_blood_panel_entities(
    result: dict[str, Any],
    encounter_text: str,
    chunks: list[SentenceChunk],
) -> dict[str, Any]:
    from libs.pipeline.blood_panel_table import (
        extract_blood_panel_table_entities,
        merge_blood_panel_entities,
    )

    panel = extract_blood_panel_table_entities(encounter_text, chunks)
    if not panel:
        return result
    merged = merge_blood_panel_entities(list(result.get("entities") or []), panel)
    if len(merged) > len(result.get("entities") or []):
        route = str(result.get("extraction_route") or "")
        suffix = "+blood-panel" if route else "blood-panel"
        result = dict(result)
        result["entities"] = merged
        result["extraction_route"] = f"{route}{suffix}" if route else suffix
    return result


def extract_entities(state: ExtractionState) -> dict[str, Any]:
    encounter_text = state.get("encounter_text") or ""
    raw_sentences = state.get("sentences") or []
    model_mode = _resolve_model_mode(state)
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

        if model_mode == "ner":
            result = _run_ner_extraction(encounter_text, chunks, state)
            if not result.get("entities"):
                fallback = _extract_lab_fallback_entities(encounter_text, chunks)
                if fallback:
                    logger.warning(
                        "NER extraction returned 0 entities; deterministic lab "
                        "fallback generated %d entities",
                        len(fallback),
                    )
                    result["entities"] = fallback
                    result["extraction_route"] = "ner+lab-fallback"
            return _enrich_with_blood_panel_entities(result, encounter_text, chunks)

        if model_mode == "auto":
            if _ner_backend_enabled():
                try:
                    ner_result = _run_ner_extraction(encounter_text, chunks, state)
                except Exception as exc:
                    logger.warning(
                        "Auto mode: NER extraction failed (%s); falling back to LLM",
                        exc,
                    )
                else:
                    if ner_result.get("entities"):
                        ner_result["extraction_route"] = "auto-ner"
                        return _enrich_with_blood_panel_entities(
                            ner_result, encounter_text, chunks
                        )
                    logger.info(
                        "Auto mode: NER returned 0 entities; falling back to LLM"
                    )
            else:
                logger.debug("Auto mode: NER backend not enabled; using LLM extractor")
            llm_result = _run_llm_extraction(encounter_text, chunks, state)
            llm_result["extraction_route"] = "auto-llm"
            return _enrich_with_blood_panel_entities(llm_result, encounter_text, chunks)

        # default: model_mode == "llm"
        result = _run_llm_extraction(encounter_text, chunks, state)
        return _enrich_with_blood_panel_entities(result, encounter_text, chunks)
    except ImportError as e:
        logger.warning("Extractor unavailable: %s", e)
        return {"entities": [], "errors": [str(e)]}
    except Exception as e:
        strict_requested_ner = model_mode == "ner" and bool(
            state.get("strict_model_version", False)
        )
        if strict_requested_ner:
            raise
        logger.exception("Entity extraction failed")
        return {"entities": [], "errors": [str(e)]}


def merge_results(state: ExtractionState) -> dict[str, Any]:
    return {
        "entities": state.get("entities", []),
        "extraction_model_name": state.get("extraction_model_name", ""),
        "extraction_model_version": state.get("extraction_model_version", ""),
        "extraction_model_requested_version": state.get(
            "extraction_model_requested_version", ""
        ),
        "extraction_model_version_mismatch": bool(
            state.get("extraction_model_version_mismatch", False)
        ),
        "extraction_route": state.get("extraction_route", ""),
        "errors": state.get("errors", []),
    }


def build_extraction_subgraph() -> CompiledStateGraph:
    g = StateGraph(ExtractionState)
    g.add_node("resolve_text_units", resolve_text_units)
    g.add_node("extract_entities", extract_entities)
    g.add_node("merge_results", merge_results)
    g.add_edge(START, "resolve_text_units")
    g.add_edge("resolve_text_units", "extract_entities")
    g.add_edge("extract_entities", "merge_results")
    g.add_edge("merge_results", END)
    return g.compile()
