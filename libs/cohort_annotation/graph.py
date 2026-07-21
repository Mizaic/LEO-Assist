"""LangGraph annotation pipeline for the cancer cohort.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Nine nodes:
  1.  pre_classify       -- deterministic EncounterClass routing
  2.  deterministic_extract -- regex lab/vitals extraction
  3.  structured_verify  -- Haiku: 'did regex miss any lab rows?'
  4.  narrative_node     -- Haiku: full narrative entity extraction
  5.  merge_and_close    -- pure Python span merge + triple closure
  6.  relation_closure   -- pure Python R16d + simple finding_site
  7.  relation_linker    -- Haiku (conditional): finding_site,
                           associated_finding, qualifies
  8.  validate           -- verbatim + schema + policy validators
  9.  finalise           -- assemble output; set annotation_complete

Conditional edges:
  pre_classify -> EMPTY -> finalise (skip all nodes)
  relation_closure -> needs_llm_rel? -> relation_linker or validate
  validate -> drop_count > 0 AND retry_count < 1 -> narrative_node
  validate -> otherwise -> finalise
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from libs.cohort_annotation.classifier import classify, EncounterClass
from libs.cohort_annotation.deterministic_extractor import (
    extract_structured_entities,
    encounter_structured_sentences,
)
from libs.cohort_annotation.prompts.narrative_v1 import NARRATIVE_SYSTEM_V1
from libs.cohort_annotation.prompts.relation_linker_v1 import RELATION_LINKER_SYSTEM_V1
from libs.cohort_annotation.prompts.structured_verify_v1 import STRUCTURED_VERIFY_SYSTEM_V1
from libs.cohort_annotation.relation_closure import (
    add_deterministic_relations,
    needs_llm_relation_pass,
)
from libs.cohort_annotation.span_closure import merge_and_close
from libs.cohort_annotation.state import AnnotationState
from libs.cohort_annotation.validators import run_all_validators

logger = logging.getLogger(__name__)

_JSON_START_RE = re.compile(r"\{", re.DOTALL)
_MAX_RETRIES = 0  # retry adds a second Bedrock call that pushes total time over the graph timeout


def _parse_json(text: str) -> dict[str, Any]:
    """Parse the first complete JSON object from an LLM response.

    Uses raw_decode so that trailing text (e.g. a second stray JSON block or
    explanation prose) after the first valid object is silently ignored instead
    of raising 'Extra data'.
    """
    m = _JSON_START_RE.search(text)
    if not m:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    obj, _ = json.JSONDecoder().raw_decode(text, m.start())
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}: {text[:200]}")
    return obj


def _build_sentences_block(sentences: list[dict[str, Any]]) -> str:
    lines = []
    for s in sentences:
        sid = s.get("sentence_id", "?")
        text = s.get("text", "").replace("\n", "\\n")
        lines.append(f"[{sid}] {text}")
    return "\n".join(lines)


def _build_coded_block(concepts: list[dict[str, Any]]) -> str:
    if not concepts:
        return "none"
    items = []
    for c in concepts:
        name = c.get("name") or ""
        labels = c.get("labels") or []
        lbl = labels[0] if labels else ""
        if name:
            items.append(f"- {name} ({lbl})")
    return "\n".join(items) if items else "none"


def _build_narrative_user_msg(state: AnnotationState) -> str:
    date = state.get("encounter_date") or "unknown"
    flags = (state.get("encounter_flags") or "").replace("\n", " | ")[:80]
    coded_block = _build_coded_block(state.get("existing_coded_concepts") or [])
    sentences_block = _build_sentences_block(state.get("sentences") or [])
    return (
        f"Encounter date: {date}\n"
        f"Encounter type: {flags}\n\n"
        f"FYI - existing coded concepts (do not under-emit narrative entities):\n"
        f"{coded_block}\n\n"
        f"Sentences:\n{sentences_block}\n\n"
        f"Annotate."
    )


def _build_structured_verify_msg(state: AnnotationState) -> str:
    sentences = state.get("sentences") or []
    structured_ents = state.get("structured_entities") or []
    struct_sents = encounter_structured_sentences(sentences)
    sentences_block = _build_sentences_block(struct_sents)
    already_found = [e.get("quote", "") for e in structured_ents]
    return (
        f"Already extracted by regex:\n"
        + "\n".join(f"  - {q}" for q in already_found)
        + f"\n\nStructured sentences only:\n{sentences_block}\n\n"
        f"Did the regex miss any lab or vitals rows?"
    )


def _build_relation_linker_msg(state: AnnotationState) -> str:
    entities = state.get("entities") or []
    sentences_block = _build_sentences_block(state.get("sentences") or [])
    ents_block = "\n".join(
        f"  {e['id']}: \"{e.get('quote','')}\" "
        f"({', '.join(e.get('labels') or [])})"
        for e in entities
    )
    return (
        f"Entities:\n{ents_block}\n\n"
        f"Sentences:\n{sentences_block}\n\n"
        f"Emit semantic relations."
    )


def _get_llm():
    from libs.llm_client.factory import create_llm
    return create_llm(tier="small")


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


def node_pre_classify(state: AnnotationState) -> AnnotationState:
    text = state.get("text") or ""
    flags = state.get("encounter_flags") or ""
    ec = classify(text, flags)
    return {**state, "encounter_class": ec.value, "errors": state.get("errors") or []}


def node_deterministic_extract(state: AnnotationState) -> AnnotationState:
    sentences = state.get("sentences") or []
    entities = extract_structured_entities(sentences)
    return {**state, "structured_entities": entities}


def node_structured_verify(state: AnnotationState) -> AnnotationState:
    sentences = state.get("sentences") or []
    if not encounter_structured_sentences(sentences):
        return {**state, "structured_missing": []}

    user_msg = _build_structured_verify_msg(state)
    llm = _get_llm()
    pid = state.get("patient_id") or ""
    try:
        resp = llm.converse(
            system=STRUCTURED_VERIFY_SYSTEM_V1,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1024,
            temperature=0.0,
            agent_task="cohort_annotation_structured_verify",
            patient_id=pid,
        )
        parsed = _parse_json(resp.text)
        missing = parsed.get("missed_entities") or []
        for e in missing:
            e.setdefault("source", "structured_verify")
        return {
            **state,
            "structured_missing": missing,
            "llm_calls": (state.get("llm_calls") or 0) + 1,
            "total_input_tokens": (state.get("total_input_tokens") or 0) + resp.input_tokens,
            "total_output_tokens": (state.get("total_output_tokens") or 0) + resp.output_tokens,
            "total_cache_read_tokens": (state.get("total_cache_read_tokens") or 0) + resp.cached_input_tokens,
        }
    except Exception as exc:
        logger.warning("structured_verify failed: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"structured_verify: {exc}")
        return {**state, "structured_missing": [], "errors": errors}


def node_narrative(state: AnnotationState) -> AnnotationState:
    user_msg = _build_narrative_user_msg(state)
    llm = _get_llm()
    pid = state.get("patient_id") or ""
    try:
        resp = llm.converse(
            system=NARRATIVE_SYSTEM_V1,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4096,
            temperature=0.0,
            agent_task="cohort_annotation_narrative",
            patient_id=pid,
        )
        parsed = _parse_json(resp.text)
        narrative_ents = parsed.get("entities") or []
        for e in narrative_ents:
            e.setdefault("source", "narrative")
        return {
            **state,
            "narrative_entities": narrative_ents,
            "llm_calls": (state.get("llm_calls") or 0) + 1,
            "total_input_tokens": (state.get("total_input_tokens") or 0) + resp.input_tokens,
            "total_output_tokens": (state.get("total_output_tokens") or 0) + resp.output_tokens,
            "total_cache_read_tokens": (state.get("total_cache_read_tokens") or 0) + resp.cached_input_tokens,
        }
    except Exception as exc:
        logger.warning("narrative node failed: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"narrative: {exc}")
        return {**state, "narrative_entities": [], "errors": errors}


def node_merge_and_close(state: AnnotationState) -> AnnotationState:
    sentences = state.get("sentences") or []
    entities = merge_and_close(
        structured_entities=state.get("structured_entities") or [],
        structured_missing=state.get("structured_missing") or [],
        narrative_entities=state.get("narrative_entities") or [],
        sentences=sentences,
    )
    return {**state, "entities": entities}


def node_relation_closure(state: AnnotationState) -> AnnotationState:
    entities = state.get("entities") or []
    relations = add_deterministic_relations(entities, state.get("relations"))
    return {**state, "relations": relations}


def node_relation_linker(state: AnnotationState) -> AnnotationState:
    user_msg = _build_relation_linker_msg(state)
    llm = _get_llm()
    pid = state.get("patient_id") or ""
    try:
        resp = llm.converse(
            system=RELATION_LINKER_SYSTEM_V1,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=2048,
            temperature=0.0,
            agent_task="cohort_annotation_relation_linker",
            patient_id=pid,
        )
        parsed = _parse_json(resp.text)
        new_rels = parsed.get("relations") or []
        for r in new_rels:
            r.setdefault("source", "relation_linker")
        existing = list(state.get("relations") or [])
        seen: set[tuple[str, str, str]] = {
            (r.get("head_id", ""), r.get("tail_id", ""), r.get("type", ""))
            for r in existing
        }
        for r in new_rels:
            key = (r.get("head_id", ""), r.get("tail_id", ""), r.get("type", ""))
            if key not in seen:
                existing.append(r)
                seen.add(key)
        return {
            **state,
            "relations": existing,
            "llm_calls": (state.get("llm_calls") or 0) + 1,
            "total_input_tokens": (state.get("total_input_tokens") or 0) + resp.input_tokens,
            "total_output_tokens": (state.get("total_output_tokens") or 0) + resp.output_tokens,
            "total_cache_read_tokens": (state.get("total_cache_read_tokens") or 0) + resp.cached_input_tokens,
        }
    except Exception as exc:
        logger.warning("relation_linker failed: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"relation_linker: {exc}")
        return {**state, "errors": errors}


def node_validate(state: AnnotationState) -> AnnotationState:
    sentences = state.get("sentences") or []
    entities, relations, drops = run_all_validators(
        entities=state.get("entities") or [],
        relations=state.get("relations") or [],
        sentences=sentences,
    )
    existing_drops = list(state.get("qa_drops") or [])
    return {
        **state,
        "entities": entities,
        "relations": relations,
        "qa_drops": existing_drops + drops,
    }


def node_finalise(state: AnnotationState) -> AnnotationState:
    return {**state, "annotation_complete": True}


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def route_after_classify(state: AnnotationState) -> str:
    ec = state.get("encounter_class") or EncounterClass.MIXED.value
    if ec == EncounterClass.EMPTY.value:
        return "finalise"
    return "deterministic_extract"


def route_after_relation_closure(state: AnnotationState) -> str:
    entities = state.get("entities") or []
    if needs_llm_relation_pass(entities):
        return "relation_linker"
    return "validate"


def route_after_validate(state: AnnotationState) -> str:
    drops = state.get("qa_drops") or []
    retry = state.get("retry_count") or 0
    if drops and retry < _MAX_RETRIES:
        return "narrative_node"
    return "finalise"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    """Return a compiled LangGraph StateGraph for the annotation pipeline."""
    g = StateGraph(AnnotationState)

    g.add_node("pre_classify",          node_pre_classify)
    g.add_node("deterministic_extract", node_deterministic_extract)
    g.add_node("structured_verify",     node_structured_verify)
    g.add_node("narrative_node",        node_narrative)
    g.add_node("merge_and_close",       node_merge_and_close)
    g.add_node("relation_closure",      node_relation_closure)
    g.add_node("relation_linker",       node_relation_linker)
    g.add_node("validate",              node_validate)
    g.add_node("finalise",              node_finalise)

    g.add_edge(START, "pre_classify")

    g.add_conditional_edges(
        "pre_classify",
        route_after_classify,
        {
            "finalise":              "finalise",
            "deterministic_extract": "deterministic_extract",
        },
    )

    g.add_edge("deterministic_extract", "structured_verify")
    g.add_edge("structured_verify",     "narrative_node")
    g.add_edge("narrative_node",        "merge_and_close")
    g.add_edge("merge_and_close",       "relation_closure")

    g.add_conditional_edges(
        "relation_closure",
        route_after_relation_closure,
        {
            "relation_linker": "relation_linker",
            "validate":        "validate",
        },
    )

    g.add_edge("relation_linker", "validate")

    g.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "narrative_node": "narrative_node",
            "finalise":       "finalise",
        },
    )

    g.add_edge("finalise", END)

    return g.compile()
