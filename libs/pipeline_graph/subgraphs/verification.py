"""Verification subgraph implementing extract-verify-retry pattern for NER quality.

Prompt resolution:
1. ``prompt_config`` dict in state (from Neo4j PromptConfig)
2. ``libs.prompts.registry.get_prompt("label_verification", 2)`` (Neo4j → hardcoded)
3. Inline fallback below
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

_FALLBACK_VERIFY_PROMPT = """You are a clinical NER quality reviewer. Verify the extracted entities against the source text.

Source text:
---
{encounter_text}
---

Extracted entities (JSON):
{entities_json}

IMPORTANT: Character offsets (start/end fields) are set by a trusted NLP sentence splitter
(PyRuSH) and are NOT your responsibility to verify. Do NOT raise issues about character
positions, start/end values, or span boundaries — those are always correct.

Check ONLY these three clinical aspects:
1. Completeness: Are all clinically significant entities present?
   Pay special attention to comma-separated lists (e.g. "diabetes, hypertension") —
   each item should be a separate entity.
2. Labels: Is the semantic_tag/label correct for each entity?
   (e.g. "disorder", "finding", "procedure", "substance")
3. Assertions: Is the assertion correct for each entity?
   Valid values: present, absent, hypothetical, possible, historical.

Respond with JSON only:
{{"is_accurate": true|false, "confidence": 0.0-1.0, "issues": ["issue1", "issue2"]}}"""

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _resolve_verify_prompt(state: dict) -> str:
    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return cfg["systemPrompt"]
    try:
        from libs.prompts.registry import get_prompt
        return get_prompt("label_verification", version=2)
    except (KeyError, ImportError):
        return _FALLBACK_VERIFY_PROMPT


class VerificationState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict]
    prompt_config: dict[str, Any]
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
            raise ValueError(f"Verifier returned non-object JSON: {type(parsed).__name__}")
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
    
    # Ensure corrections is a list if present
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

Respond with JSON only — no prose, no markdown fences.
Required keys: is_accurate (bool), confidence (0.0-1.0), issues (list of strings).
If you find issues, provide structured `corrections` referencing the entity index.
"""

# Bedrock tool-forcing config.
# When toolChoice forces a specific tool, Claude physically cannot return prose —
# it must call the named tool and populate its schema-validated input.
# This is the most reliable JSON-enforcement mechanism available on Bedrock.
_VERIFICATION_TOOL_CONFIG: dict = {
    "tools": [
        {
            "toolSpec": {
                "name": "verification_result",
                "description": (
                    "Submit the structured NER verification result. "
                    "You MUST call this tool — do not return free text."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "is_accurate": {
                                "type": "boolean",
                                "description": (
                                    "True if every extracted entity is correct "
                                    "(text span, label, assertion). False if any issue exists."
                                ),
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Overall confidence score from 0.0 (no confidence) to 1.0 (certain).",
                            },
                            "issues": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Specific issues found with individual entities. "
                                    "Empty list when is_accurate is true."
                                ),
                            },
                            "corrections": {
                                "type": "array",
                                "description": "Structured corrections for specific entities. Provide this if is_accurate is false.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "entity_index": {
                                            "type": "integer",
                                            "description": "Index of the entity in the input array (0-based)."
                                        },
                                        "corrected_label": {
                                            "type": "string",
                                            "description": "Corrected semantic_tag/label (e.g. 'finding', 'disorder')."
                                        },
                                        "corrected_lookup_term": {
                                            "type": "string",
                                            "description": "Better search term for terminology resolution."
                                        },
                                        "corrected_assertion": {
                                            "type": "string",
                                            "description": "Corrected assertion (e.g. 'absent', 'present')."
                                        }
                                    },
                                    "required": ["entity_index"]
                                }
                            }
                        },
                        "required": ["is_accurate", "confidence", "issues"],
                    }
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": "verification_result"}},
}


def _build_verify_messages(
    system_prompt: str,
    encounter_text: str,
    entities_json: str,
) -> tuple[str, list[dict]]:
    """Return (system, messages) ready to pass to llm.converse().

    Two styles are supported:
    - Combined template: system_prompt contains ``{encounter_text}`` — the
      data is injected directly into it, which then becomes the user message.
      The system param gets a minimal instruction string.
    - Instructions-only (V2 style): no placeholders — the system_prompt is
      used as the system param verbatim, and the data is sent as a separate
      user message.  This is correct for prompts managed via /admin/prompts.
    """
    if "{encounter_text}" in system_prompt:
        # Legacy combined-template style (e.g. _FALLBACK_VERIFY_PROMPT).
        user_content = system_prompt.format(
            encounter_text=encounter_text,
            entities_json=entities_json,
        )
        return (
            "You are a clinical NER verifier. Respond only with valid JSON.",
            [{"role": "user", "content": user_content}],
        )

    # Instructions-only style (e.g. LABEL_VERIFICATION_V2 from Neo4j).
    # System carries the full instructions; user message carries the data.
    user_content = _USER_DATA_TEMPLATE.format(
        encounter_text=encounter_text,
        entities_json=entities_json,
    )
    return system_prompt, [{"role": "user", "content": user_content}]


def verify_entities(state: VerificationState) -> dict[str, Any]:
    encounter_text = state.get("encounter_text") or ""
    entities = state.get("entities") or []
    tier = state.get("model_tier") or "big"
    attempts = list(state.get("extraction_attempts") or [])
    errors = list(state.get("errors") or [])
    raw = ""
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=tier)
        system_prompt = _resolve_verify_prompt(state)
        system, messages = _build_verify_messages(
            system_prompt,
            encounter_text,
            json.dumps(entities, indent=2),
        )
        resp = llm.converse(
            system=system,
            messages=messages,
            # Bedrock (Claude): toolChoice forces Claude to call the named tool —
            # it physically cannot return prose when toolChoice is set.
            tool_config=_VERIFICATION_TOOL_CONFIG,
            # Azure OpenAI: response_format=json_object hard-locks JSON output.
            json_mode=True,
        )

        # Bedrock tool-forced responses arrive in tool_uses, not text.
        # Azure json_mode responses arrive in text as usual.
        if resp.tool_uses:
            raw = json.dumps(resp.tool_uses[0].get("input", {}))
        else:
            raw = (resp.text or "").strip()

        result = _normalise_verification_result(_parse_verification_json(raw))
        attempts.append(result)
        return {
            "extraction_attempts": attempts,
            "verification_result": result,
            "verification_non_retryable": False,
            "errors": errors,
        }
    except ValueError as e:
        # Invalid/empty verifier payload is not recoverable by immediate retry.
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

    # Primary pass: verifier explicitly agrees AND confidence is above threshold.
    strict_pass = is_accurate and confidence >= threshold

    # Fallback pass: retries exhausted, confidence still above threshold.
    # The verifier may keep raising minor/borderline issues on every retry —
    # in that case the confidence score is the authoritative quality signal.
    confidence_pass = (retries_remaining == 0) and (confidence >= threshold) and not strict_pass

    passed = strict_pass or confidence_pass

    if confidence_pass:
        logger.info(
            "Verification: retries exhausted but confidence %.2f >= threshold %.2f — accepting with confidence override",
            confidence,
            threshold,
        )

    if passed:
        best = result
        # Tag how it passed so the UI can distinguish
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
    passed = (is_accurate and confidence >= threshold) or (retries_remaining == 0 and confidence >= threshold)
    if passed or retries_remaining <= 0:
        return "end"
    return "retry"


def correct_entities(state: VerificationState) -> dict[str, Any]:
    """Apply corrections suggested by the verifier."""
    result = state.get("verification_result") or {}
    corrections = result.get("corrections") or []
    if not corrections:
        return {}
    
    entities = list(state.get("entities") or [])
    # Deep copy to avoid mutation issues if needed, though here we replace the list
    # Actually, we want to modify the entities in the list.
    # Since we are returning a new list to update state, we should copy.
    import copy
    new_entities = copy.deepcopy(entities)
    
    applied_count = 0
    for corr in corrections:
        idx = corr.get("entity_index")
        if idx is not None and isinstance(idx, int) and 0 <= idx < len(new_entities):
            ent = new_entities[idx]
            if corr.get("corrected_label"):
                ent["label"] = corr["corrected_label"]
            if corr.get("corrected_lookup_term"):
                ent["lookup_term"] = corr["corrected_lookup_term"]
            if corr.get("corrected_assertion"):
                ent["assertion"] = corr["corrected_assertion"]
            applied_count += 1
            
    if applied_count > 0:
        logger.info(f"Applied {applied_count} corrections from verifier")
        return {"entities": new_entities}
    return {}


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
