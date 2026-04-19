"""Verification subgraph implementing extract-verify-retry pattern for NER quality.

Prompt resolution:
1. ``prompt_config`` dict in state (typically loaded from Neo4j PromptConfig)
2. ``libs.prompts.registry.get_prompt("verification", 1)`` from Neo4j
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

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.prompts.verification_output_schema import VERIFICATION_OUTPUT_SCHEMA
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)

_MAX_VERIFICATION_TOOL_ITERATIONS = max(
    1,
    int(os.getenv("VERIFICATION_TOOL_MAX_ITERATIONS", "4")),
)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _resolve_verify_prompt_spec(state: dict) -> dict[str, Any]:
    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return {
            "system_prompt": cfg["systemPrompt"],
            "prompt_name": str(cfg.get("name") or "custom_verification"),
            "prompt_version": cfg.get("version"),
            "prompt_source": "state.prompt_config",
            "prompt_config_id": cfg.get("id") or state.get("prompt_config_id"),
        }

    from libs.prompts.registry import get_prompt

    return {
        "system_prompt": get_prompt("verification", version=1),
        "prompt_name": "verification",
        "prompt_version": 1,
        "prompt_source": "neo4j_registry",
        "prompt_config_id": None,
    }


class VerificationState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict]
    prompt_config: dict[str, Any]
    verification_prompt: dict[str, Any]
    verification_tool_trace: list[dict[str, Any]]
    model_tier: str
    max_retries: int
    confidence_threshold: float
    extraction_attempts: list[dict]
    verification_result: dict
    verification_non_retryable: bool
    is_verified: bool
    errors: list[str]


def _parse_verification_json(raw: str) -> dict[str, Any]:
    """Parse model verification JSON from plain/fenced/mixed content."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty verifier response")

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
            if isinstance(parsed, dict):
                return parsed
            raise ValueError(
                f"Verifier returned non-object JSON: {type(parsed).__name__}"
            )
        except Exception:
            continue

    raise ValueError(f"Verifier returned invalid JSON: {text[:220]}")


def _normalise_verification_result(result: dict[str, Any]) -> dict[str, Any]:
    """Coerce verifier output into stable shape used by downstream nodes."""
    normalised = dict(result)
    normalised.setdefault("is_accurate", False)
    try:
        normalised["confidence"] = float(normalised.get("confidence", 0.0))
    except Exception:
        normalised["confidence"] = 0.0

    issues = normalised.get("issues")
    if isinstance(issues, list):
        normalised["issues"] = [str(i) for i in issues]
    elif issues is None:
        normalised["issues"] = []
    else:
        normalised["issues"] = [str(issues)]

    corrections = normalised.get("corrections")
    if corrections is not None and not isinstance(corrections, list):
        normalised["corrections"] = []

    return normalised


_USER_DATA_TEMPLATE = """\
Encounter text:
---
{encounter_text}
---

Entities to verify (JSON):
{entities_json}

Note: character offsets (start/end) are set by a trusted NLP tool — do NOT check or
raise issues about span positions. Only assess clinical accuracy: completeness, labels,
and assertions.

This is a materiality-based review:
- Only mark the extraction inaccurate for clinically meaningful errors.
- Do NOT fail for mere preference or precision improvements.
- A lookup_term is acceptable if it is clinically faithful and likely SNOMED-resolvable.
- If you can only improve wording slightly, keep is_accurate=true.
- When uncertain whether a lookup_term is SNOMED-representable or materially misleading,
  call the `lookup_snomed` tool before making the final judgment.

When providing corrections, use drop=true for any entity that:
  - Is a vague improvement or progress statement ("knee is improving", "doing well", "feeling better")
  - Is administrative narrative with no clinical concept ("discussed results", "letter filed", "reviewed")
  - Cannot plausibly be represented as a SNOMED CT concept — i.e. a terminology lookup would fail
Do NOT drop clinically codeable findings, disorders, procedures, or substances.

Examples:
- "medial CPPD" on an X-ray may be acceptable as extracted if clinically faithful, even if
  you might personally prefer a different label or synonym.
- "knee is improving" should usually be dropped, not rewritten into an awkward pseudo-SNOMED term.

Respond with JSON only — no prose, no markdown fences.
Required keys: is_accurate (bool), confidence (0.0-1.0), issues (list of strings).
If you find issues, provide structured `corrections` referencing the entity index.
"""

_LOOKUP_SNOMED_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entity_index": {
            "type": "integer",
            "description": "Entity index being checked (0-based).",
        },
        "query": {
            "type": "string",
            "description": "Term or phrase to look up in SNOMED.",
        },
        "expected_label": {
            "type": "string",
            "description": "Optional expected semantic tag to bias search.",
        },
        "reason": {
            "type": "string",
            "description": "Short explanation of why lookup is needed.",
        },
    },
    "required": ["entity_index", "query"],
}

_VERIFICATION_TOOL_CONFIG: dict = {
    "tools": [
        {
            "toolSpec": {
                "name": "lookup_snomed",
                "description": (
                    "Look up a candidate clinical term in the SNOMED terminology service "
                    "before deciding whether it is materially acceptable."
                ),
                "inputSchema": {"json": _LOOKUP_SNOMED_INPUT_SCHEMA},
            }
        },
        {
            "toolSpec": {
                "name": "verification_result",
                "description": (
                    "Submit the structured verification result once you are ready to judge."
                ),
                "inputSchema": {"json": VERIFICATION_OUTPUT_SCHEMA},
            }
        },
    ],
}


def _build_verify_messages(
    system_prompt: str,
    encounter_text: str,
    entities_json: str,
) -> tuple[str, list[dict]]:
    """Return (system, messages) ready to pass to llm.converse()."""
    if "{encounter_text}" in system_prompt:
        user_content = system_prompt.format(
            encounter_text=sanitise_for_prompt(encounter_text, max_chars=16_000),
            entities_json=sanitise_for_prompt(entities_json, max_chars=12_000),
        )
        return (
            "You are a clinical NER verifier. Respond only with valid JSON.",
            [{"role": "user", "content": user_content}],
        )

    user_content = _USER_DATA_TEMPLATE.format(
        encounter_text=sanitise_for_prompt(encounter_text, max_chars=16_000),
        entities_json=sanitise_for_prompt(entities_json, max_chars=12_000),
    )
    return system_prompt, [{"role": "user", "content": user_content}]


def _build_tool_result_block(
    tool_use_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    safe_text = sanitise_for_prompt(
        json.dumps(payload, ensure_ascii=True), max_chars=4000
    )
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"text": safe_text}],
        }
    }


def _execute_lookup_snomed(
    tool_input: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    query = str(tool_input.get("query") or "").strip()
    expected_label = str(tool_input.get("expected_label") or "").strip() or None
    entity_index = tool_input.get("entity_index")
    reason = str(tool_input.get("reason") or "").strip()
    if not query:
        payload = {"ok": False, "error": "empty_query", "candidates": []}
        trace = {
            "tool_name": "lookup_snomed",
            "entity_index": entity_index,
            "query": query,
            "expected_label": expected_label,
            "reason": reason,
            "candidate_count": 0,
            "ok": False,
        }
        return payload, trace

    client = TerminologyClient(timeout=15.0, max_retries=1)
    candidates = client.resolve(
        [query],
        expected_tags={query: expected_label} if expected_label else None,
    ).get(query, [])
    top = candidates[:5]
    payload = {
        "ok": True,
        "query": query,
        "expected_label": expected_label,
        "candidates": [
            {
                "concept_id": c.concept_id,
                "term": c.term,
                "semantic_tag": c.semantic_tag,
                "score": round(float(c.score), 4),
                "read_code": c.read_code,
            }
            for c in top
        ],
    }
    trace = {
        "tool_name": "lookup_snomed",
        "entity_index": entity_index,
        "query": query,
        "expected_label": expected_label,
        "reason": reason,
        "candidate_count": len(top),
        "top_candidate": payload["candidates"][0] if payload["candidates"] else None,
        "ok": True,
    }
    return payload, trace


def verify_entities(state: VerificationState) -> dict[str, Any]:
    encounter_text = state.get("encounter_text") or ""
    entities = state.get("entities") or []
    tier = state.get("model_tier") or "big"
    attempts = list(state.get("extraction_attempts") or [])
    errors = list(state.get("errors") or [])
    raw = ""
    prompt_spec: dict[str, Any] = {}
    tool_trace = list(state.get("verification_tool_trace") or [])
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=tier)
        prompt_spec = _resolve_verify_prompt_spec(state)
        system_prompt = str(prompt_spec["system_prompt"])
        system, messages = _build_verify_messages(
            system_prompt,
            encounter_text,
            json.dumps(entities, indent=2),
        )

        for _ in range(_MAX_VERIFICATION_TOOL_ITERATIONS):
            resp = llm.converse(
                system=system,
                messages=deepcopy(messages),
                tool_config=_VERIFICATION_TOOL_CONFIG,
                json_mode=True,
                agent_task="v3_pipeline_ner_verifier",
            )

            if resp.tool_uses:
                assistant_content: list[dict[str, Any]] = []
                if resp.text:
                    assistant_content.append({"text": resp.text})
                assistant_content.extend(
                    {"toolUse": tool_use} for tool_use in resp.tool_uses
                )
                messages.append({"role": "assistant", "content": assistant_content})

                final_tool_use = next(
                    (
                        tool_use
                        for tool_use in resp.tool_uses
                        if tool_use.get("name") == "verification_result"
                    ),
                    None,
                )
                if final_tool_use is not None:
                    raw = json.dumps(final_tool_use.get("input", {}))
                    break

                tool_results: list[dict[str, Any]] = []
                for tool_use in resp.tool_uses:
                    if tool_use.get("name") != "lookup_snomed":
                        tool_results.append(
                            _build_tool_result_block(
                                str(tool_use.get("toolUseId") or ""),
                                {
                                    "ok": False,
                                    "error": f"unsupported_tool:{tool_use.get('name')}",
                                },
                            )
                        )
                        continue

                    payload, trace = _execute_lookup_snomed(
                        tool_use.get("input", {}) or {}
                    )
                    tool_trace.append(trace)
                    tool_results.append(
                        _build_tool_result_block(
                            str(tool_use.get("toolUseId") or ""), payload
                        )
                    )

                if not tool_results:
                    raise ValueError(
                        "Verifier returned tool_use without executable tool calls"
                    )
                messages.append({"role": "user", "content": tool_results})
                continue

            raw = (resp.text or "").strip()
            break
        else:
            raise ValueError(
                f"verification_tool_iteration_limit_exceeded: max {_MAX_VERIFICATION_TOOL_ITERATIONS}"
            )

        result = _normalise_verification_result(_parse_verification_json(raw))
        attempts.append(result)
        return {
            "extraction_attempts": attempts,
            "verification_result": result,
            "verification_prompt": prompt_spec,
            "verification_tool_trace": tool_trace,
            "verification_non_retryable": False,
            "errors": errors,
        }
    except ValueError as e:
        logger.warning("Verification failed: %s", e)
        errors.append(str(e))
        failed_result = {
            "is_accurate": False,
            "confidence": 0.0,
            "issues": [f"verification_parse_error: {e}"],
            "raw_response": (raw[:4000] if raw else ""),
        }
        attempts.append(failed_result)
        return {
            "extraction_attempts": attempts,
            "verification_result": failed_result,
            "verification_prompt": prompt_spec,
            "verification_tool_trace": tool_trace,
            "verification_non_retryable": True,
            "errors": errors,
        }
    except Exception as e:
        logger.exception("Verification failed")
        errors.append(str(e))
        failed_result = {
            "is_accurate": False,
            "confidence": 0.0,
            "issues": [f"verification_parse_error: {e}"],
            "raw_response": (raw[:4000] if raw else ""),
        }
        attempts.append(failed_result)
        return {
            "extraction_attempts": attempts,
            "verification_result": failed_result,
            "verification_prompt": prompt_spec,
            "verification_tool_trace": tool_trace,
            "verification_non_retryable": False,
            "errors": errors,
        }


def evaluate_result(state: VerificationState) -> dict[str, Any]:
    result = state.get("verification_result") or {}
    threshold = float(state.get("confidence_threshold") or 0.8)
    max_retries = int(state.get("max_retries") or 2)
    attempts = state.get("extraction_attempts") or []
    is_accurate = result.get("is_accurate", False)
    confidence = float(result.get("confidence", 0.0))
    retries_remaining = max(0, max_retries + 1 - len(attempts))

    strict_pass = is_accurate and confidence >= threshold
    confidence_pass = (
        (retries_remaining == 0) and (confidence >= threshold) and not strict_pass
    )
    passed = strict_pass or confidence_pass

    if confidence_pass:
        logger.info(
            "Verification: retries exhausted but confidence %.2f >= threshold %.2f — accepting with confidence override",
            confidence,
            threshold,
        )

    if passed:
        best = result
        if confidence_pass:
            best = dict(best)
            best["pass_reason"] = "confidence_override"
    elif attempts:
        best = max(attempts, key=lambda a: float(a.get("confidence", 0)))
    else:
        best = result

    return {
        "is_verified": passed,
        "verification_result": best,
        "verification_tool_trace": state.get("verification_tool_trace") or [],
    }


def _route_after_evaluate(state: VerificationState) -> str:
    if state.get("verification_non_retryable"):
        return "end"
    result = state.get("verification_result") or {}
    threshold = float(state.get("confidence_threshold") or 0.8)
    max_retries = int(state.get("max_retries") or 2)
    attempts = state.get("extraction_attempts") or []
    is_accurate = result.get("is_accurate", False)
    confidence = float(result.get("confidence", 0.0))
    retries_remaining = max(0, max_retries + 1 - len(attempts))
    passed = (is_accurate and confidence >= threshold) or (
        retries_remaining == 0 and confidence >= threshold
    )
    if passed or retries_remaining <= 0:
        return "end"
    return "retry"


def correct_entities(state: VerificationState) -> dict[str, Any]:
    """Apply corrections suggested by the verifier, including entity drops."""
    import copy

    result = state.get("verification_result") or {}
    corrections = result.get("corrections") or []
    if not corrections:
        return {}

    entities = list(state.get("entities") or [])
    new_entities = copy.deepcopy(entities)

    drop_indices: set[int] = set()
    patch_count = 0

    for corr in corrections:
        idx = corr.get("entity_index")
        if not (isinstance(idx, int) and 0 <= idx < len(new_entities)):
            continue

        if corr.get("drop"):
            drop_indices.add(idx)
            logger.info(
                "correct_entities: dropping entity %d (%s) — not SNOMED-representable",
                idx,
                new_entities[idx].get("text", ""),
            )
            continue

        ent = new_entities[idx]
        if corr.get("corrected_label"):
            ent["label"] = corr["corrected_label"]
            ent["semantic_tag"] = corr["corrected_label"]
        if corr.get("corrected_lookup_term"):
            ent["lookup_term"] = corr["corrected_lookup_term"]
        if corr.get("corrected_assertion"):
            ent["assertion"] = corr["corrected_assertion"]
        patch_count += 1

    if drop_indices:
        new_entities = [e for i, e in enumerate(new_entities) if i not in drop_indices]
        logger.info(
            "correct_entities: dropped %d entities, %d patched",
            len(drop_indices),
            patch_count,
        )
    elif patch_count == 0:
        return {}
    else:
        logger.info("correct_entities: patched %d entities", patch_count)

    return {"entities": new_entities}


def build_verification_subgraph() -> CompiledStateGraph:
    g = StateGraph(VerificationState)
    g.add_node("verify_entities", verify_entities)
    g.add_node("evaluate_result", evaluate_result)
    g.add_node("correct_entities", correct_entities)

    g.add_edge(START, "verify_entities")
    g.add_edge("verify_entities", "evaluate_result")
    g.add_conditional_edges(
        "evaluate_result",
        _route_after_evaluate,
        {"retry": "correct_entities", "end": END},
    )
    g.add_edge("correct_entities", "verify_entities")
    return g.compile()
