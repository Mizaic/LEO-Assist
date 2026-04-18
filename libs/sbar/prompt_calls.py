"""LLM call wrappers for the three SBAR prompts.

Centralised so the orchestrator stays focused on flow control and so the
prompt-rendering rules (CONTEXT serialisation, sanitisation, fallback
handling) live in one place.

Each function returns a dict with:
  - ``markdown``  - the section text
  - ``raw``       - the raw LLM JSON (for storage/audit)
  - ``error``     - a string if the call failed, otherwise None
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from libs.llm_client.json_helper import invoke_llm_json
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.prompts.registry import get_prompt
from libs.sbar.source_resolver import (
    ResolvedCode,
    ResolvedSituation,
    ResolvedSource,
)

logger = logging.getLogger(__name__)


_PROMPT_NAME_SITUATION = "sbar_situation"
_PROMPT_NAME_BACKGROUND = "sbar_background"
_PROMPT_NAME_RECOMMENDATION = "sbar_recommendation"


# ---------------------------------------------------------------------------
# Context serialisation
# ---------------------------------------------------------------------------


def _serialise_situation_context(
    resolved: ResolvedSituation,
    *,
    extra_context: dict[str, Any] | None = None,
) -> str:
    body = {
        "patient": {
            "id": resolved.patient_id,
            "gender": resolved.patient_summary.get("gender"),
            "birth_date": resolved.patient_summary.get("birth_date"),
        },
        "artifacts": [
            {k: sanitise_for_prompt(v) if isinstance(v, str) else v
             for k, v in artefact.items()}
            for artefact in resolved.artifacts
        ],
        "extra": extra_context or {},
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _serialise_background_context(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None = None,
) -> str:
    body = {
        "referring_specialty": referring_specialty,
        "codes": [
            {
                "concept_id": c.concept_id,
                "term": c.term,
                "semantic_tag": c.semantic_tag,
                "assertion": c.assertion,
                "evidence": sanitise_for_prompt(c.evidence or ""),
                "source": {"type": c.source_label, "id": c.source_id},
                "confidence": c.confidence,
            }
            for c in codes
        ],
        "sources": [
            {
                "type": s.source_label,
                "id": s.source_id,
                "text": sanitise_for_prompt(s.text or "")[:4000],
                "metadata": s.metadata,
                "has_codes": s.has_codes(),
            }
            for s in sources
        ],
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _serialise_recommendation_context(
    *,
    situation_md: str,
    background_md: str,
    assessment_md: str,
    assessment_rules: list[dict[str, Any]],
    guideline_titles: list[str],
    guidelines: list[str],
) -> str:
    body = {
        "situation": situation_md,
        "background": background_md,
        "assessment": assessment_md,
        "assessment_rules": assessment_rules,
        "guideline_titles": guideline_titles,
        "guidelines": guidelines,
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


PromptFetcher = Callable[[str], str]


# SBAR prompts are pinned to v2 -- plain-English narrative with inline
# [date] markers only (no encounter / document ids). v1 stays seeded for
# audit / rollback. See DO-LEO-AI-191.
_SBAR_PROMPT_VERSIONS: dict[str, int] = {
    _PROMPT_NAME_SITUATION: 2,
    _PROMPT_NAME_BACKGROUND: 2,
    _PROMPT_NAME_RECOMMENDATION: 2,
}


def _default_prompt(name: str) -> str:
    return get_prompt(name, version=_SBAR_PROMPT_VERSIONS.get(name, 1))


async def call_situation(
    resolved: ResolvedSituation,
    *,
    extra_context: dict[str, Any] | None = None,
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
) -> dict[str, Any]:
    system = prompt_fetcher(_PROMPT_NAME_SITUATION)
    user = _serialise_situation_context(resolved, extra_context=extra_context)
    raw = await invoker(
        system,
        user,
        max_tokens=512,
        temperature=0.0,
        agent_task="sbar_situation",
        patient_id=patient_id,
    )
    if "error" in raw:
        return {"markdown": "", "raw": raw, "error": raw["error"]}
    md = (raw.get("situation_markdown") or "").strip()
    return {
        "markdown": md,
        "raw": raw,
        "error": None if md else "missing_situation_markdown",
    }


async def call_background(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None = None,
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
) -> dict[str, Any]:
    system = prompt_fetcher(_PROMPT_NAME_BACKGROUND)
    user = _serialise_background_context(
        sources, codes, referring_specialty=referring_specialty
    )
    raw = await invoker(
        system,
        user,
        max_tokens=1024,
        temperature=0.0,
        agent_task="sbar_background",
        patient_id=patient_id,
    )
    if "error" in raw:
        return {"markdown": "", "raw": raw, "error": raw["error"]}
    md = (raw.get("background_markdown") or "").strip()
    return {
        "markdown": md,
        "raw": raw,
        "error": None if md else "missing_background_markdown",
    }


async def call_recommendation(
    *,
    situation_md: str,
    background_md: str,
    assessment_md: str,
    assessment_rules: list[dict[str, Any]],
    guideline_titles: list[str],
    guidelines: list[str],
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
) -> dict[str, Any]:
    system = prompt_fetcher(_PROMPT_NAME_RECOMMENDATION)
    user = _serialise_recommendation_context(
        situation_md=situation_md,
        background_md=background_md,
        assessment_md=assessment_md,
        assessment_rules=assessment_rules,
        guideline_titles=guideline_titles,
        guidelines=guidelines,
    )
    raw = await invoker(
        system,
        user,
        max_tokens=1024,
        temperature=0.0,
        agent_task="sbar_recommendation",
        patient_id=patient_id,
    )
    if "error" in raw:
        return {
            "markdown": "",
            "actions": [],
            "raw": raw,
            "error": raw["error"],
        }
    md = (raw.get("recommendation_markdown") or "").strip()
    actions = list(raw.get("actions") or [])
    return {
        "markdown": md,
        "actions": actions,
        "raw": raw,
        "error": None if md else "missing_recommendation_markdown",
    }
