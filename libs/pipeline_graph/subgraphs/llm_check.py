"""Lightweight single-turn LLM checks for extraction and coding quality."""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.nlp.sentence_splitter import is_referral_procedure_phrase

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


class LLMCheckState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    prompt_config: dict[str, Any]
    model_tier: str
    llm_check_mode: str
    llm_check_result: dict[str, Any]
    llm_check_changes: list[dict[str, Any]]
    errors: list[str]


def _label_is_procedure(label: str) -> bool:
    return label.strip().lower().replace(" ", "_") == "procedure"


def _normalise_referral_procedure_assertion(
    *,
    label: str,
    text: str,
    assertion: str,
) -> str:
    cleaned_assertion = assertion.strip().lower()
    if (
        cleaned_assertion == "possible"
        and _label_is_procedure(label)
        and is_referral_procedure_phrase(text)
    ):
        return "present"
    return cleaned_assertion


def _parse_json_result(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}

    candidates: list[str] = []
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    if text.startswith("{") and text.endswith("}"):
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
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"Invalid JSON output from LLM check: {text[:220]}")


def _resolve_prompt(mode: str, state: LLMCheckState) -> str:
    cfg = state.get("prompt_config") or {}
    prompt = cfg.get("systemPrompt")
    if prompt:
        return str(prompt)

    try:
        from libs.prompts.registry import get_prompt

        if mode == "coding":
            return get_prompt("coding_check", version=1)
        return get_prompt("extraction_check", version=1)
    except Exception:
        if mode == "coding":
            from libs.prompts.coding_check_v1 import CODING_CHECK_SYSTEM_V1

            return CODING_CHECK_SYSTEM_V1
        from libs.prompts.extraction_check_v1 import EXTRACTION_CHECK_SYSTEM_V1

        return EXTRACTION_CHECK_SYSTEM_V1


def _resolve_span(encounter_text: str, needle: str) -> tuple[int, int]:
    cleaned = needle.strip()
    if not cleaned:
        return 0, 1
    haystack = encounter_text.lower()
    idx = haystack.find(cleaned.lower())
    if idx >= 0:
        return idx, idx + len(cleaned)
    return 0, len(cleaned)


def _run_check(state: LLMCheckState, mode: str) -> dict[str, Any]:
    encounter_text = str(state.get("encounter_text") or "")
    entities = list(state.get("entities") or [])
    tier = str(state.get("model_tier") or "small")
    prompt = _resolve_prompt(mode, state)
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
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=True)}],
            temperature=0.0,
            max_tokens=1200,
            json_mode=True,
        )
        result = _parse_json_result(response.text or "{}")
        return {"llm_check_result": result, "errors": errors}
    except Exception as exc:
        errors.append(str(exc))
        return {"llm_check_result": {}, "errors": errors}


def _apply_extraction_check(state: LLMCheckState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    result = state.get("llm_check_result") or {}
    changes: list[dict[str, Any]] = []

    drop_indices = set()
    for idx in result.get("drop", []):
        if isinstance(idx, int) and 0 <= idx < len(entities):
            drop_indices.add(idx)

    if drop_indices:
        for idx in sorted(drop_indices):
            changes.append({"type": "drop", "index": idx, "reason": "ner_false_positive"})
        entities = [entity for i, entity in enumerate(entities) if i not in drop_indices]

    for row in result.get("correct_assertion", []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        assertion = str(row.get("assertion") or "").strip()
        if not (isinstance(idx, int) and 0 <= idx < len(entities) and assertion):
            continue
        current = entities[idx]
        final_assertion = _normalise_referral_procedure_assertion(
            label=str(current.get("label") or ""),
            text=str(current.get("text") or current.get("normalized") or ""),
            assertion=assertion,
        )
        entities[idx]["assertion"] = final_assertion
        if final_assertion != assertion.strip().lower():
            entities[idx]["_assertion_guard"] = "referral_procedure"
        entities[idx]["_llm_check_source"] = "assertion_corrected"
        changes.append({"type": "assertion_corrected", "index": idx, "assertion": final_assertion})

    for row in result.get("correct_label", []):
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

    encounter_text = str(state.get("encounter_text") or "")
    for row in result.get("add", []):
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip()
        if not text or not label:
            continue
        start, end = _resolve_span(encounter_text, text)
        assertion = str(row.get("assertion") or "present")
        final_assertion = _normalise_referral_procedure_assertion(
            label=label,
            text=text,
            assertion=assertion,
        )
        new_entity = {
            "text": text,
            "label": label,
            "semantic_tag": label,
            "start": start,
            "end": end,
            "assertion": final_assertion,
            "confidence": float(row.get("confidence") or 0.6),
            "normalized": str(row.get("lookup_term") or text),
            "lookup_term": str(row.get("lookup_term") or text),
            "_llm_check_source": "llm_added",
        }
        if final_assertion != assertion.strip().lower():
            new_entity["_assertion_guard"] = "referral_procedure"
        entities.append(new_entity)
        changes.append({"type": "added", "text": text, "label": label})

    return {"entities": entities, "llm_check_changes": changes}


def _apply_coding_check(state: LLMCheckState) -> dict[str, Any]:
    entities = deepcopy(state.get("entities") or [])
    result = state.get("llm_check_result") or {}
    changes: list[dict[str, Any]] = []

    drop_indices = set()
    for idx in result.get("drop", []):
        if isinstance(idx, int) and 0 <= idx < len(entities):
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
        entities = [entity for i, entity in enumerate(entities) if i not in drop_indices]

    return {"entities": entities, "llm_check_changes": changes}


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

