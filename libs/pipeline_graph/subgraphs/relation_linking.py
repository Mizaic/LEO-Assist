"""Relation linking subgraph. Atlas: DO-8E641A9E, DO-49256B13, DI-6ACD24D2.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.json_helper import _extract_json
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.ner.body_structure_guard import suppress_orphan_body_structures
from libs.relations.policy import (
    allowed_relation_types,
    canonicalise_relations,
    is_relation_allowed,
)

logger = logging.getLogger(__name__)
_MODEL_CONFIDENCE_THRESHOLD = float(
    os.getenv("RELATION_MODEL_CONFIDENCE_THRESHOLD", "0.72")
)
_RELATION_MODEL_PATH = os.getenv("RELATION_MODEL_PATH", "").strip()
_RELATION_LINKER_MAX_TOKENS = int(os.getenv("RELATION_LINKER_MAX_TOKENS", "8000"))
_RELATION_LINKER_ENTITY_CAP = int(os.getenv("RELATION_LINKER_ENTITY_CAP", "80"))
_RELATION_MODEL_CACHE: dict[str, Any] | None = None
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


class RelationLinkState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    prompt_config: dict[str, Any]
    model_tier: str
    relation_link_result: dict[str, Any]
    relation_model_result: dict[str, Any]
    snomed_candidates: list[dict[str, Any]]
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


def _parse_relation_linker_result(raw: str) -> dict[str, Any]:
    """Parse relation-linker JSON without failing the pipeline stage."""
    text = (raw or "").strip()
    if not text:
        return {"relations": [], "suppress": []}

    candidates: list[str] = []
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    if text.startswith("{"):
        candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = _extract_json(candidate)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
    logger.warning(
        "relation_linker returned invalid JSON; using model-only relations",
    )
    return {}


def _collect_snomed_rows(state: RelationLinkState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, ent in enumerate(state.get("entities") or []):
        if not isinstance(ent, dict):
            continue
        for rel in ent.get("__snomed_relations") or []:
            if not isinstance(rel, dict):
                continue
            tail = rel.get("target_idx")
            rel_type = str(rel.get("type") or "").strip().lower()
            if not isinstance(tail, int) or not rel_type:
                continue
            rows.append(
                {
                    "head_idx": i,
                    "tail_idx": tail,
                    "type": rel_type,
                    "confidence": float(rel.get("confidence") or 0.9),
                    "extraction_method": "snomed",
                }
            )
    if rows:
        return rows
    return [
        row for row in (state.get("snomed_candidates") or []) if isinstance(row, dict)
    ]


def _normalise_judge_result(
    parsed: dict[str, Any],
    snomed_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not parsed:
        return {"relations": list(snomed_rows), "suppress": []}
    if "confirmed" in parsed or "additional" in parsed:
        confirmed = [r for r in (parsed.get("confirmed") or []) if isinstance(r, dict)]
        additional = [
            r for r in (parsed.get("additional") or []) if isinstance(r, dict)
        ]
        for row in confirmed:
            row.setdefault("extraction_method", "snomed+llm")
        for row in additional:
            row.setdefault("extraction_method", "llm")
        return {
            "relations": confirmed + additional,
            "suppress": [
                i for i in (parsed.get("suppress") or []) if isinstance(i, int)
            ],
        }
    return parsed


def _run_linker(
    state: RelationLinkState,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    encounter_text = str(state.get("encounter_text") or "")
    entities = list(state.get("entities") or [])
    if not entities:
        return {"relation_link_result": {"relations": [], "suppress": []}, "errors": []}

    prompt = _resolve_prompt(state)
    tier = str(state.get("model_tier") or "small")
    llm_entities = entities
    if _RELATION_LINKER_ENTITY_CAP > 0:
        llm_entities = entities[:_RELATION_LINKER_ENTITY_CAP]
    payload: dict[str, Any] = {
        "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
        "entities": llm_entities,
    }
    if candidates:
        payload["candidates"] = candidates
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
            max_tokens=_RELATION_LINKER_MAX_TOKENS,
            json_mode=True,
            agent_task="v3_pipeline_relation_linker",
        )
        parsed = _parse_relation_linker_result(response.text or "")
        if not isinstance(parsed, dict):
            parsed = {}
        return {"relation_link_result": parsed, "errors": errors}
    except Exception as exc:
        logger.warning("relation_linker LLM call failed: %s", exc)
        return {
            "relation_link_result": {"relations": [], "suppress": []},
            "errors": errors,
        }


def _entity_label(entity: dict[str, Any]) -> str:
    return str(entity.get("label") or entity.get("semantic_tag") or "")


def _is_suppressible_site(entity: dict[str, Any]) -> bool:
    """True for body-structure or inferred sites. Findings stay persistable."""
    if bool(entity.get("inferred")):
        return True
    label = _entity_label(entity).lower().replace(" ", "_")
    return label == "body_structure"


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


def _pick_relation_type(
    source: dict[str, Any],
    target: dict[str, Any],
    pair_prior: dict[str, Any],
    allowed_types: list[str],
) -> tuple[str | None, float]:
    """Pick a relation type. No-prior pairs only get nearby finding_site."""
    has_offsets = isinstance(source.get("start"), int) and isinstance(
        target.get("start"), int
    )
    if not pair_prior:
        if not has_offsets or "finding_site" not in allowed_types:
            return None, 0.0
        distance = abs(int(source["start"]) - int(target["start"]))
        if distance > 500:
            return None, 0.0
        return "finding_site", max(0.62, 0.9 - min(distance, 1200) / 3000.0)

    rel_type = max(allowed_types, key=lambda t: float(pair_prior.get(t) or 0.0))
    total = sum(float(v) for v in pair_prior.values()) or 1.0
    prior = float(pair_prior.get(rel_type) or 0.0) / total
    confidence = max(0.82, min(0.95, 0.55 + prior))
    if has_offsets:
        distance = abs(int(source.get("start") or 0) - int(target.get("start") or 0))
        confidence = max(0.62, 0.9 - min(distance, 1200) / 3000.0)
    return rel_type, confidence


def _model_predict_relations(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic predictor: pair_priors, else nearby finding_site only."""
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
            allowed_types = [
                rt
                for rt in allowed_relation_types()
                if is_relation_allowed(
                    source_label=src_label, target_label=tgt_label, relation_type=rt
                )[0]
            ]
            if not allowed_types:
                continue
            rel_type, conf = _pick_relation_type(
                source, target, pair_prior, allowed_types
            )
            if rel_type is None:
                continue
            relations.append(
                {
                    "head_idx": i,
                    "tail_idx": j,
                    "type": rel_type,
                    "confidence": round(conf, 4),
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
    """Merge model and LLM rows. Same triple keeps the higher confidence."""
    merged: dict[tuple[int, int, str], dict[str, Any]] = {}
    tagged: list[tuple[dict[str, Any], str]] = [(r, "model") for r in model_rows] + [
        (r, "llm") for r in llm_rows
    ]
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
        tagged_method = str(row.get("extraction_method") or method)
        if prev is None:
            merged[key] = {
                "head_idx": h,
                "tail_idx": t,
                "type": relation_type,
                "confidence": confidence,
                "extraction_method": tagged_method,
            }
            continue
        combined_method = prev.get("extraction_method") or tagged_method
        if combined_method != tagged_method:
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


def _row_indices(row: dict[str, Any], count: int) -> tuple[int, int] | None:
    head_idx = row.get("head_idx")
    tail_idx = row.get("tail_idx")
    if not (
        isinstance(head_idx, int)
        and isinstance(tail_idx, int)
        and 0 <= head_idx < count
        and 0 <= tail_idx < count
        and head_idx != tail_idx
    ):
        return None
    return head_idx, tail_idx


def _add_entity_relation(
    entities: list[dict[str, Any]],
    row: dict[str, Any],
    runtime_types: frozenset[str],
    changes: list[dict[str, Any]],
) -> None:
    relation_type = str(row.get("type") or "").strip().lower()
    if relation_type not in runtime_types:
        return
    idxs = _row_indices(row, len(entities))
    if idxs is None:
        return
    head_idx, tail_idx = idxs
    head = entities[head_idx]
    tail = entities[tail_idx]
    label_ok, _ = is_relation_allowed(
        source_label=_entity_label(head),
        target_label=_entity_label(tail),
        relation_type=relation_type,
    )
    if not label_ok:
        return
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
        return
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


def _apply_relation_linking(state: RelationLinkState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    model_result = state.get("relation_model_result") or {}
    llm_result = _normalise_judge_result(state.get("relation_link_result") or {}, [])
    runtime_types = allowed_relation_types()
    result_rows = _merge_model_and_llm(
        list(model_result.get("relations") or []),
        list(llm_result.get("relations") or []),
    )
    changes: list[dict[str, Any]] = []
    suppress = {
        i
        for i in list(model_result.get("suppress") or [])
        + list(llm_result.get("suppress") or [])
        if isinstance(i, int)
    }
    for row in result_rows:
        if isinstance(row, dict):
            _add_entity_relation(entities, row, runtime_types, changes)
    for idx in suppress:
        if 0 <= idx < len(entities) and _is_suppressible_site(entities[idx]):
            entities[idx]["_relation_suppressed"] = True
    suppress_orphan_body_structures(entities)
    return {"entities": entities, "relation_changes": changes}


def _apply_and_return(
    state: RelationLinkState,
    model_updates: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(state)
    merged.update(model_updates)
    merged.update(updates)
    merged_state = RelationLinkState(**merged)
    return {**model_updates, **updates, **_apply_relation_linking(merged_state)}


def relation_linking(state: RelationLinkState) -> dict[str, Any]:
    snomed_rows = _collect_snomed_rows(state)
    if snomed_rows:
        raw = _run_linker(state, snomed_rows)
        judged = _normalise_judge_result(
            raw.get("relation_link_result") or {}, snomed_rows
        )
        updates = {**raw, "relation_link_result": judged}
        model_updates = {"relation_model_result": {"relations": [], "suppress": []}}
        return _apply_and_return(state, model_updates, updates)

    model_updates = _run_model_first(state)
    model_rows = list(
        (model_updates.get("relation_model_result") or {}).get("relations") or []
    )
    high_conf = [
        row
        for row in model_rows
        if float(row.get("confidence") or 0.0) >= _MODEL_CONFIDENCE_THRESHOLD
    ]
    updates = (
        _run_linker(state)
        if len(high_conf) < max(1, min(3, len(model_rows)))
        else {"relation_link_result": {"relations": [], "suppress": []}, "errors": []}
    )
    return _apply_and_return(state, model_updates, updates)


def build_relation_linking_subgraph() -> CompiledStateGraph:
    g = StateGraph(RelationLinkState)
    g.add_node("relation_linking", relation_linking)
    g.add_edge(START, "relation_linking")
    g.add_edge("relation_linking", END)
    return g.compile()
