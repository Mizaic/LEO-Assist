"""Lightweight single-turn LLM checks for extraction and coding quality.

Atlas trace:
  DO: DO-8620A68B
  Also implements: DO-93E086B0
  DI: DI-2D9F5064, DI-5A802C83, DI-F2C18D2E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8620A68B")
"""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.json_helper import _extract_json
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.nlp.sentence_splitter import is_referral_procedure_phrase
from libs.ner.scope_guard import SUPPRESSED, reclassify_assertion
from libs.pipeline.form_checkbox_seed import is_taught_checkbox
from libs.pipeline_graph.subgraphs._extraction_check_adds import (
    apply_added_entities,
    normalise_referral_procedure_assertion,
)
from libs.pipeline_graph.subgraphs._extraction_check_relations import (
    apply_relation_updates,
    renumber_relations,
)

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?:\.(?:\s|$)|\n)")
_REFERRAL_CLINIC_RE = re.compile(
    r"\b(fast\s*track|2ww|two\s*week\s*wait)\b.{0,48}\b(referral|clinic)\b",
    re.IGNORECASE,
)
_SUSPECTED_LANGUAGE_RE = re.compile(
    r"\b(suspected|possible|probable|query|\br\/o\b|rule\s*out)\b",
    re.IGNORECASE,
)
_CONFIRMED_DIAGNOSIS_RE = re.compile(
    r"\b(confirmed|diagnosed|diagnosis|histology|biopsy\s+(confirmed|showed)|"
    r"proven|evidence\s+of)\b",
    re.IGNORECASE,
)

_LLM_CHECK_MAX_TOKENS = int(os.getenv("LLM_CHECK_MAX_TOKENS", "8000"))
_LLM_CHECK_ENTITY_CAP = int(os.getenv("LLM_CHECK_ENTITY_CAP", "80"))


class LLMCheckState(TypedDict, total=False):
    encounter_text: str
    sentences: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    prompt_config: dict[str, Any]
    model_tier: str
    llm_check_mode: str
    llm_check_result: dict[str, Any]
    llm_check_changes: list[dict[str, Any]]
    relation_changes: list[dict[str, Any]]
    has_extraction_changes: bool
    has_coding_issues: bool
    errors: list[str]


def _parse_json_result(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}

    candidates: list[str] = []
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    if text.startswith("{"):
        candidates.append(text)
    object_match = _JSON_OBJECT_RE.search(text)
    if object_match:
        candidates.append(object_match.group(0).strip())
    candidates.append(text)

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
        "llm_check returned invalid JSON; continuing without LLM corrections",
    )
    return {}


def _resolve_prompt(mode: str, state: LLMCheckState) -> str:
    prompt_name = "coding_check" if mode == "coding" else "extraction_check"
    cfg = state.get("prompt_config") or {}
    prompt = cfg.get("systemPrompt")
    if prompt:
        from libs.prompts.registry import compose_prompt_with_annotation_guidelines

        return compose_prompt_with_annotation_guidelines(prompt_name, str(prompt))

    try:
        from libs.prompts.registry import get_prompt

        if mode == "coding":
            return get_prompt(prompt_name, version=1)
        return get_prompt(prompt_name, version=2)
    except Exception:
        from libs.prompts.registry import compose_prompt_with_annotation_guidelines

        if mode == "coding":
            from libs.prompts.coding_check_v1 import CODING_CHECK_SYSTEM_V1

            return compose_prompt_with_annotation_guidelines(
                prompt_name, CODING_CHECK_SYSTEM_V1
            )
        from libs.prompts.extraction_check_v1 import EXTRACTION_CHECK_SYSTEM_V2

        return compose_prompt_with_annotation_guidelines(
            prompt_name, EXTRACTION_CHECK_SYSTEM_V2
        )


def _extract_sentence_window(
    encounter_text: str,
    start: int,
    end: int,
    margin: int = 300,
) -> str:
    win_start = max(0, start - margin)
    win_end = min(len(encounter_text), end + margin)

    left = encounter_text[win_start:start]
    boundary = _SENTENCE_BOUNDARY_RE.search(left[::-1])
    if boundary:
        win_start = start - boundary.start()

    right = encounter_text[end:win_end]
    boundary = _SENTENCE_BOUNDARY_RE.search(right)
    if boundary:
        win_end = end + boundary.end()

    return encounter_text[win_start:win_end]


def _apply_scope_guard_after_extraction_check(
    encounter_text: str,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    to_remove: list[int] = []
    for idx, ent in enumerate(entities):
        if is_taught_checkbox(ent):
            continue
        assertion = str(ent.get("assertion") or "present").strip().lower()
        if assertion not in ("present", ""):
            continue
        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", 0) or 0)
        sentence_text = _extract_sentence_window(encounter_text, start, end)
        new_assertion = reclassify_assertion(
            entity_semantic_tag=str(ent.get("label") or ""),
            entity_assertion=assertion,
            sentence_text=sentence_text,
            entity_text=str(ent.get("text") or ent.get("normalized") or ""),
        )
        if new_assertion == SUPPRESSED:
            to_remove.append(idx)
            changes.append(
                {
                    "type": "drop",
                    "index": idx,
                    "reason": "scope_guard_post_extraction_check",
                }
            )
        elif new_assertion is not None:
            ent["assertion"] = new_assertion
            changes.append(
                {
                    "type": "assertion_corrected",
                    "index": idx,
                    "assertion": new_assertion,
                }
            )
    if not to_remove:
        return entities
    return [ent for i, ent in enumerate(entities) if i not in set(to_remove)]


def _is_referral_suspicion_context(sentence_text: str) -> bool:
    lowered = sentence_text.strip()
    if not lowered:
        return False
    has_referral_context = bool(
        _REFERRAL_CLINIC_RE.search(lowered) or is_referral_procedure_phrase(lowered)
    )
    if not has_referral_context:
        return False
    if not _SUSPECTED_LANGUAGE_RE.search(lowered):
        return False
    return not _CONFIRMED_DIAGNOSIS_RE.search(lowered)


def _apply_referral_inference_guard(
    encounter_text: str,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    to_remove: list[int] = []
    for idx, ent in enumerate(entities):
        label = str(ent.get("label") or "").strip().lower()
        assertion = str(ent.get("assertion") or "present").strip().lower()
        if label != "disorder" or assertion not in {"possible", "hypothetical"}:
            continue
        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", 0) or 0)
        sentence_text = _extract_sentence_window(encounter_text, start, end)
        if not _is_referral_suspicion_context(sentence_text):
            continue
        to_remove.append(idx)
        changes.append(
            {
                "type": "drop",
                "index": idx,
                "reason": "referral_suspicion_disorder_inference",
            }
        )
    if not to_remove:
        return entities
    drop_set = set(to_remove)
    return [ent for i, ent in enumerate(entities) if i not in drop_set]


def _run_check(state: LLMCheckState, mode: str) -> dict[str, Any]:
    encounter_text = str(state.get("encounter_text") or "")
    entities = list(state.get("entities") or [])
    tier = str(state.get("model_tier") or "small")
    prompt = _resolve_prompt(mode, state)
    llm_entities = entities
    if _LLM_CHECK_ENTITY_CAP > 0:
        llm_entities = entities[:_LLM_CHECK_ENTITY_CAP]
    payload = {
        "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
        "entities": llm_entities,
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
            max_tokens=_LLM_CHECK_MAX_TOKENS,
            json_mode=True,
            agent_task="v3_pipeline_llm_check",
        )
        result = _parse_json_result(response.text or "{}")
        return {"llm_check_result": result, "errors": errors}
    except Exception as exc:
        logger.warning("llm_check LLM call failed: %s", exc)
        return {"llm_check_result": {}, "errors": errors}


def _apply_assertion_corrections(
    rows: Any, entities: list[dict[str, Any]], changes: list[dict[str, Any]]
) -> None:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        assertion = str(row.get("assertion") or "").strip()
        if not (isinstance(idx, int) and 0 <= idx < len(entities) and assertion):
            continue
        current = entities[idx]
        final_assertion = normalise_referral_procedure_assertion(
            label=str(current.get("label") or ""),
            text=str(current.get("text") or current.get("normalized") or ""),
            assertion=assertion,
        )
        entities[idx]["assertion"] = final_assertion
        if final_assertion != assertion.strip().lower():
            entities[idx]["_assertion_guard"] = "referral_procedure"
        entities[idx]["_llm_check_source"] = "assertion_corrected"
        changes.append(
            {"type": "assertion_corrected", "index": idx, "assertion": final_assertion}
        )


def _apply_label_corrections(
    rows: Any, entities: list[dict[str, Any]], changes: list[dict[str, Any]]
) -> None:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        label = str(row.get("label") or "").strip()
        if not (isinstance(idx, int) and 0 <= idx < len(entities) and label):
            continue
        entities[idx]["label"] = label
        entities[idx]["semantic_tag"] = label
        entities[idx]["_llm_check_source"] = "label_corrected"
        changes.append({"type": "label_corrected", "index": idx, "label": label})


def _apply_extraction_check(state: LLMCheckState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    result = state.get("llm_check_result") or {}
    changes: list[dict[str, Any]] = []
    relation_changes: list[dict[str, Any]] = []

    drop_indices = set()
    for idx in result.get("drop", []):
        if not (isinstance(idx, int) and 0 <= idx < len(entities)):
            continue
        if is_taught_checkbox(entities[idx]):
            continue
        drop_indices.add(idx)

    # The model numbers facts as it was shown them, so every edit by index
    # must land before any fact is removed.
    _apply_assertion_corrections(result.get("correct_assertion"), entities, changes)
    _apply_label_corrections(result.get("correct_label"), entities, changes)
    apply_relation_updates(entities, result, relation_changes)
    shown = list(entities)

    if drop_indices:
        for idx in sorted(drop_indices):
            changes.append(
                {"type": "drop", "index": idx, "reason": "ner_false_positive"}
            )
        entities = [
            entity for i, entity in enumerate(entities) if i not in drop_indices
        ]

    encounter_text = str(state.get("encounter_text") or "")
    apply_added_entities(
        result.get("add"), encounter_text, state.get("sentences"), entities, changes
    )

    entities = _apply_referral_inference_guard(encounter_text, entities, changes)
    entities = _apply_scope_guard_after_extraction_check(
        encounter_text, entities, changes
    )
    renumber_relations(shown, entities)

    return {
        "entities": entities,
        "llm_check_changes": changes,
        "relation_changes": relation_changes,
        "has_extraction_changes": bool(changes or relation_changes),
    }


def _apply_coding_check(state: LLMCheckState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    result = state.get("llm_check_result") or {}
    changes: list[dict[str, Any]] = []

    drop_indices = set()
    for idx in result.get("drop", []):
        if not (isinstance(idx, int) and 0 <= idx < len(entities)):
            continue
        if is_taught_checkbox(entities[idx]):
            continue
        drop_indices.add(idx)

    for row in result.get("force_review", []):
        idx = row if isinstance(row, int) else None
        if idx is None and isinstance(row, dict):
            idx = row.get("index")
        if not (isinstance(idx, int) and 0 <= idx < len(entities)):
            continue
        entities[idx]["_tier_override"] = 2
        entities[idx]["_tier_override_reason"] = "llm_coding_check_force_review"
        entities[idx]["_llm_check_source"] = "coding_force_review"
        changes.append({"type": "force_review", "index": idx})

    if drop_indices:
        for idx in sorted(drop_indices):
            changes.append({"type": "drop", "index": idx, "reason": "coding_mismatch"})
        entities = [
            entity for i, entity in enumerate(entities) if i not in drop_indices
        ]

    return {
        "entities": entities,
        "llm_check_changes": changes,
        "has_coding_issues": bool(changes),
    }


def extraction_check(state: LLMCheckState) -> dict[str, Any]:
    updates = _run_check(state, mode="extraction")
    merged = dict(state)
    merged.update(updates)
    merged_state = LLMCheckState(**merged)
    return {**updates, **_apply_extraction_check(merged_state)}


def coding_check(state: LLMCheckState) -> dict[str, Any]:
    updates = _run_check(state, mode="coding")
    merged = dict(state)
    merged.update(updates)
    merged_state = LLMCheckState(**merged)
    return {**updates, **_apply_coding_check(merged_state)}


def build_extraction_check_subgraph() -> CompiledStateGraph:
    g = StateGraph(LLMCheckState)
    g.add_node("extraction_check", extraction_check)
    g.add_edge(START, "extraction_check")
    g.add_edge("extraction_check", END)
    return g.compile()


def build_coding_check_subgraph() -> CompiledStateGraph:
    g = StateGraph(LLMCheckState)
    g.add_node("coding_check", coding_check)
    g.add_edge(START, "coding_check")
    g.add_edge("coding_check", END)
    return g.compile()
