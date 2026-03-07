"""Verification subgraph implementing extract-verify-retry pattern for NER quality.

Prompt resolution:
1. ``prompt_config`` dict in state (from Neo4j PromptConfig)
2. ``libs.prompts.registry.get_prompt("label_verification", 2)`` (Neo4j → hardcoded)
3. Inline fallback below
"""

from __future__ import annotations

import json
import logging
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

Check ONLY these aspects (do NOT evaluate SNOMED or terminology codes):
1. Text spans: Does each entity's text exactly match a substring of the source?
2. Completeness: For comma-separated lists (e.g. "diabetes, hypertension"), are all items extracted?
3. Labels: Is the semantic_tag/label correct for each entity?
4. Assertions: Is the assertion (present/absent/hypothetical) correct?

Respond with JSON only:
{{"is_accurate": true|false, "confidence": 0.0-1.0, "issues": ["issue1", "issue2"]}}"""


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
    is_verified: bool
    errors: list[str]


def verify_entities(state: VerificationState) -> dict[str, Any]:
    encounter_text = state.get("encounter_text") or ""
    entities = state.get("entities") or []
    tier = state.get("model_tier") or "big"
    attempts = list(state.get("extraction_attempts") or [])
    errors = list(state.get("errors") or [])
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=tier)
        system_prompt = _resolve_verify_prompt(state)
        prompt = system_prompt.format(
            encounter_text=encounter_text,
            entities_json=json.dumps(entities, indent=2),
        )
        resp = llm.converse(
            system="You are a clinical NER verifier. Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        attempts.append(result)
        return {
            "extraction_attempts": attempts,
            "verification_result": result,
            "errors": errors,
        }
    except Exception as e:
        logger.exception("Verification failed")
        errors.append(str(e))
        return {"extraction_attempts": attempts, "errors": errors}


def evaluate_result(state: VerificationState) -> dict[str, Any]:
    result = state.get("verification_result") or {}
    threshold = float(state.get("confidence_threshold") or 0.8)
    max_retries = int(state.get("max_retries") or 2)
    attempts = state.get("extraction_attempts") or []
    is_accurate = result.get("is_accurate", False)
    confidence = float(result.get("confidence", 0.0))
    passed = is_accurate and confidence >= threshold
    if passed:
        best = result
    elif attempts:
        best = max(attempts, key=lambda a: float(a.get("confidence", 0)))
    else:
        best = result
    return {
        "is_verified": passed,
        "verification_result": best,
    }


def _route_after_evaluate(state: VerificationState) -> str:
    result = state.get("verification_result") or {}
    threshold = float(state.get("confidence_threshold") or 0.8)
    max_retries = int(state.get("max_retries") or 2)
    attempts = state.get("extraction_attempts") or []
    passed = result.get("is_accurate", False) and float(result.get("confidence", 0)) >= threshold
    retries_remaining = max(0, max_retries + 1 - len(attempts))
    if passed or retries_remaining <= 0:
        return "end"
    return "retry"


def build_verification_subgraph() -> CompiledStateGraph:
    g = StateGraph(VerificationState)
    g.add_node("verify_entities", verify_entities)
    g.add_node("evaluate_result", evaluate_result)
    g.add_edge(START, "verify_entities")
    g.add_edge("verify_entities", "evaluate_result")
    g.add_conditional_edges(
        "evaluate_result",
        _route_after_evaluate,
        {"retry": "verify_entities", "end": END},
    )
    return g.compile()
