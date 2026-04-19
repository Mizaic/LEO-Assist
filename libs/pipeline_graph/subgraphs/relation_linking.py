"""Relation linking subgraph for extracted entities."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.relations.policy import (
    allowed_relation_types,
    canonicalise_relations,
    is_relation_allowed,
)

logger = logging.getLogger(__name__)

_ALLOWED_RELATION_TYPES = allowed_relation_types()
_MODEL_CONFIDENCE_THRESHOLD = float(
    os.getenv("RELATION_MODEL_CONFIDENCE_THRESHOLD", "0.72")
)
_RELATION_MODEL_PATH = os.getenv("RELATION_MODEL_PATH", "").strip()
_RELATION_MODEL_CACHE: dict[str, Any] | None = None


class RelationLinkState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    prompt_config: dict[str, Any]
    model_tier: str
    relation_link_result: dict[str, Any]
    relation_model_result: dict[str, Any]
    relation_changes: list[dict[str, Any]]
    errors: list[str]


def _resolve_prompt(state: RelationLinkState) -> str:
    cfg = state.get("prompt_config") or {}
    prompt = cfg.get("systemPrompt")
    if prompt:
        from libs.prompts.registry import compose_prompt_with_annotation_guidelines

        return compose_prompt_with_annotation_guidelines(
            "relation_linking", str(prompt)
        )
    try:
        from libs.prompts.registry import get_prompt

        return get_prompt("relation_linking", version=1)
    except Exception:
        from libs.prompts.registry import compose_prompt_with_annotation_guidelines
        from libs.prompts.relation_linking_v1 import RELATION_LINKING_SYSTEM_V1

        return compose_prompt_with_annotation_guidelines(
            "relation_linking", RELATION_LINKING_SYSTEM_V1
        )


def _build_compound_lookup(head_text: str, tail_text: str) -> str:
    h = (head_text or "").strip()
    t = (tail_text or "").strip()
    if not h:
        return t
    if not t:
        return h
    if h.lower() in t.lower():
        return h
    if t.lower() in h.lower():
        return h
    return f"{t} {h}".strip()


def _run_linker(state: RelationLinkState) -> dict[str, Any]:
    encounter_text = str(state.get("encounter_text") or "")
    entities = list(state.get("entities") or [])
    if not entities:
        return {"relation_link_result": {"relations": [], "suppress": []}, "errors": []}

    prompt = _resolve_prompt(state)
    tier = str(state.get("model_tier") or "small")
    payload = {
        "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
        "entities": entities,
    }
    errors = list(state.get("errors") or [])
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=tier)
        response = llm.converse(
            system=prompt,
            messages=[
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)}
            ],
            temperature=0.0,
            max_tokens=900,
            json_mode=True,
            agent_task="v3_pipeline_relation_linker",
        )
        raw = response.text or "{}"
        parsed = json.loads(raw) if raw.strip().startswith("{") else {}
        if not isinstance(parsed, dict):
            parsed = {}
        return {"relation_link_result": parsed, "errors": errors}
    except Exception as exc:
        errors.append(str(exc))
        return {"relation_link_result": {"relations": [], "suppress": []}, "errors": errors}


def _entity_label(entity: dict[str, Any]) -> str:
    return str(entity.get("label") or entity.get("semantic_tag") or "")


def _load_relation_model() -> dict[str, Any]:
    global _RELATION_MODEL_CACHE
    if _RELATION_MODEL_CACHE is not None:
        return _RELATION_MODEL_CACHE
    if not _RELATION_MODEL_PATH:
        _RELATION_MODEL_CACHE = {}
        return _RELATION_MODEL_CACHE
    path = Path(_RELATION_MODEL_PATH)
    if not path.exists():
        _RELATION_MODEL_CACHE = {}
        return _RELATION_MODEL_CACHE
    try:
        _RELATION_MODEL_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _RELATION_MODEL_CACHE = {}
    return _RELATION_MODEL_CACHE


def _model_predict_relations(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic relation predictor (model-first path).

    This keeps runtime deterministic and available even when the LLM tier is
    unavailable. We still run policy validation before persistence.
    """
    relations: list[dict[str, Any]] = []
    model = _load_relation_model()
    pair_priors = dict(model.get("pair_priors") or {})
    for i, source in enumerate(entities):
        src_label = _entity_label(source)
        for j, target in enumerate(entities):
            if i == j:
                continue
            tgt_label = _entity_label(target)
            pair_key = (
                f"{str(src_label).strip().lower()}->"
                f"{str(tgt_label).strip().lower()}"
            )
            pair_prior = dict(pair_priors.get(pair_key) or {})
            allowed_types: list[str] = []
            for relation_type in _ALLOWED_RELATION_TYPES:
                allowed, _ = is_relation_allowed(
                    source_label=src_label,
                    target_label=tgt_label,
                    relation_type=relation_type,
                )
                if allowed:
                    allowed_types.append(relation_type)
            if not allowed_types:
                continue
            relation_type = allowed_types[0]
            if pair_prior:
                relation_type = max(
                    allowed_types,
                    key=lambda item: float(pair_prior.get(item) or 0.0),
                )
            # Slight preference for nearby entities when character offsets exist.
            confidence = 0.82
            if pair_prior:
                total = sum(float(v) for v in pair_prior.values()) or 1.0
                prior = float(pair_prior.get(relation_type) or 0.0) / total
                confidence = max(confidence, min(0.95, 0.55 + prior))
            if isinstance(source.get("start"), int) and isinstance(target.get("start"), int):
                distance = abs(int(source.get("start") or 0) - int(target.get("start") or 0))
                confidence = max(0.62, 0.9 - min(distance, 1200) / 3000.0)
            relations.append(
                {
                    "head_idx": i,
                    "tail_idx": j,
                    "type": relation_type,
                    "confidence": round(confidence, 4),
                }
            )
    return {"relations": relations, "suppress": []}


def _run_model_first(state: RelationLinkState) -> dict[str, Any]:
    entities = list(state.get("entities") or [])
    if not entities:
        return {"relation_model_result": {"relations": [], "suppress": []}}
    model_result = _model_predict_relations(entities)
    return {"relation_model_result": model_result}


def _merge_model_and_llm(
    model_rows: list[dict[str, Any]],
    llm_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge model and LLM rows, preserving extraction method provenance.

    Per DI-2D9F5064 (runtime relation linking method disclosure), every merged
    relation carries `extraction_method` = "model" | "llm" | "model+llm" so
    reviewers can calibrate scepticism. When both sources produce the same
    (head, tail, type) the higher-confidence row wins and method becomes
    "model+llm".
    """
    merged: dict[tuple[int, int, str], dict[str, Any]] = {}
    tagged: list[tuple[dict[str, Any], str]] = (
        [(r, "model") for r in model_rows] + [(r, "llm") for r in llm_rows]
    )
    for row, method in tagged:
        if not isinstance(row, dict):
            continue
        h = row.get("head_idx")
        t = row.get("tail_idx")
        relation_type = str(row.get("type") or "").strip().lower()
        if not isinstance(h, int) or not isinstance(t, int):
            continue
        key = (h, t, relation_type)
        confidence = float(row.get("confidence") or 0.0)
        prev = merged.get(key)
        if prev is None:
            merged[key] = {
                "head_idx": h,
                "tail_idx": t,
                "type": relation_type,
                "confidence": confidence,
                "extraction_method": method,
            }
            continue
        combined_method = prev.get("extraction_method") or method
        if combined_method != method:
            combined_method = "model+llm"
        if float(prev.get("confidence") or 0.0) < confidence:
            merged[key] = {
                "head_idx": h,
                "tail_idx": t,
                "type": relation_type,
                "confidence": confidence,
                "extraction_method": combined_method,
            }
        else:
            prev["extraction_method"] = combined_method
    return list(merged.values())


def _apply_relation_linking(state: RelationLinkState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    model_result = state.get("relation_model_result") or {}
    llm_result = state.get("relation_link_result") or {}
    result_rows = _merge_model_and_llm(
        list(model_result.get("relations") or []),
        list(llm_result.get("relations") or []),
    )
    changes: list[dict[str, Any]] = []
    suppress = {
        i
        for i in list(model_result.get("suppress") or []) + list(llm_result.get("suppress") or [])
        if isinstance(i, int)
    }

    for row in result_rows:
        if not isinstance(row, dict):
            continue
        head_idx = row.get("head_idx")
        tail_idx = row.get("tail_idx")
        relation_type = str(row.get("type") or "").strip().lower()
        if relation_type not in _ALLOWED_RELATION_TYPES:
            continue
        if not (
            isinstance(head_idx, int)
            and isinstance(tail_idx, int)
            and 0 <= head_idx < len(entities)
            and 0 <= tail_idx < len(entities)
            and head_idx != tail_idx
        ):
            continue
        head = entities[head_idx]
        tail = entities[tail_idx]
        head_relations = list(head.get("__relations") or [])
        relation = {
            "type": relation_type,
            "target_text": str(tail.get("text") or ""),
            "target_idx": tail_idx,
            "confidence": float(row.get("confidence") or 0.6),
            "extraction_method": str(row.get("extraction_method") or "model"),
        }
        canonical = canonicalise_relations(head_relations + [relation], len(entities))
        if len(canonical) == len(head_relations):
            continue
        head["__relations"] = canonical
        if relation_type == "finding_site":
            head["body_site"] = str(tail.get("text") or "")
            head["lookup_term"] = _build_compound_lookup(
                str(head.get("text") or ""), str(tail.get("text") or "")
            )
        changes.append(
            {
                "type": "relation_added",
                "index": head_idx,
                "relation_type": relation_type,
                "target_index": tail_idx,
            }
        )

    for idx in suppress:
        if 0 <= idx < len(entities):
            entities[idx]["_relation_suppressed"] = True

    return {"entities": entities, "relation_changes": changes}


def relation_linking(state: RelationLinkState) -> dict[str, Any]:
    model_updates = _run_model_first(state)
    model_rows = list((model_updates.get("relation_model_result") or {}).get("relations") or [])
    high_conf = [
        row
        for row in model_rows
        if float(row.get("confidence") or 0.0) >= _MODEL_CONFIDENCE_THRESHOLD
    ]
    # LLM fallback only when model confidence is low or sparse.
    updates = (
        _run_linker(state)
        if len(high_conf) < max(1, min(3, len(model_rows)))
        else {"relation_link_result": {"relations": [], "suppress": []}, "errors": []}
    )
    merged = dict(state)
    merged.update(model_updates)
    merged.update(updates)
    merged_state = RelationLinkState(**merged)
    return {**model_updates, **updates, **_apply_relation_linking(merged_state)}


def build_relation_linking_subgraph() -> CompiledStateGraph:
    g = StateGraph(RelationLinkState)
    g.add_node("relation_linking", relation_linking)
    g.add_edge(START, "relation_linking")
    g.add_edge("relation_linking", END)
    return g.compile()
