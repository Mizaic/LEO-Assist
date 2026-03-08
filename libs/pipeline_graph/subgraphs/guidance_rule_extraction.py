"""NICE → AppropriatenessRule extraction subgraph.

Three-node LangGraph pipeline that converts a single NICE Recommendation into
structured, SNOMED-coded rule criteria ready to be written to Neo4j.

Nodes
-----
resolve_prompt
    Loads the ``guidance_rule_extraction`` PromptConfig from Neo4j (via the
    prompts registry).  Falls back to the hardcoded V1 text if Neo4j is
    unavailable.

extract_criteria
    Calls the dual-model consensus pipeline (Haiku + GPT-5 mini, Sonnet
    arbitration) with the resolved prompt.  Parses the LLM output into:
    ``{"present": [...], "absent": [...], "action": "..."|null}``

code_snomed
    For each criterion term calls ``GET /terminology/search`` with the
    appropriate ``semantic_tag`` filter:

    - present / absent criteria → tags: finding, disorder, observable entity, situation
    - action                    → tag: procedure

    Returns coded lists with ``snomed_concept_id``, ``preferred_term``, and
    ``semantic_tag`` for each resolved term.  Terms that do not resolve are
    included with ``snomed_concept_id: null`` so the caller can decide whether
    to skip or surface a warning.

State keys consumed by ``guidance_rule_generator.py`` downstream
----------------------------------------------------------------
``coded_criteria`` → dict with keys:
    ``present``  list[CriterionResult]
    ``absent``   list[CriterionResult]
    ``action``   ActionResult | None

where::

    CriterionResult = {
        "term": str,               # plain-text term from LLM
        "snomed_concept_id": str | None,
        "preferred_term":   str,
        "semantic_tag":     str,
    }
    ActionResult = CriterionResult  # same shape, semantic_tag always "procedure"

Prompt resolution order
-----------------------
1. ``state["prompt_config"]["systemPrompt"]`` (injected by parent graph)
2. ``libs.prompts.registry.get_prompt("guidance_rule_extraction", version=1)``
   which itself tries Neo4j first, then falls back to the Python constant.
3. Inline constant (never edited at runtime).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

_TERMINOLOGY_URL = os.getenv("TERMINOLOGY_API_URL", "http://terminology-api:8001")

# Semantic tags that are valid for criteria (present / absent) —
# findings, disorders, observable entities, and contextual situations.
_CRITERIA_TAGS = ["finding", "disorder", "observable entity", "situation"]

# Semantic tag used when coding the recommended action.
_ACTION_TAGS = ["procedure"]

_FALLBACK_SYSTEM_PROMPT = (
    "You are a clinical decision-support analyst. "
    "Read the NICE recommendation and extract:\n"
    "1. present: clinical criteria that must be in the patient's record.\n"
    "2. absent: clinical findings that exclude the recommendation.\n"
    "3. action: the recommended clinical procedure (or null).\n"
    'Return ONLY JSON: {"present": [...], "absent": [...], "action": "..."|null}'
)


# ── State ──────────────────────────────────────────────────────────────────────

class CriterionResult(TypedDict, total=False):
    term: str
    snomed_concept_id: str | None
    preferred_term: str
    semantic_tag: str


class CodedCriteria(TypedDict, total=False):
    present: list[CriterionResult]
    absent: list[CriterionResult]
    action: CriterionResult | None


class GuidanceRuleExtractionState(TypedDict, total=False):
    # ── Inputs ──
    recommendation: dict[str, Any]
    """Full recommendation dict: id, verbatim, title, urgency, strength,
    section_title, chapter_title."""
    guideline_id: str
    prompt_config: dict[str, Any] | None
    """Optional PromptConfig dict injected by the parent graph.  When present,
    its ``systemPrompt`` key overrides the registry lookup."""

    # ── Intermediate ──
    system_prompt: str
    raw_criteria: dict[str, Any] | None
    """Parsed LLM output: {present, absent, action}."""

    # ── Outputs ──
    coded_criteria: CodedCriteria | None
    errors: list[str]


# ── Node 1: resolve_prompt ─────────────────────────────────────────────────────

def resolve_prompt(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Load the guidance_rule_extraction PromptConfig from Neo4j or use fallback."""
    errors: list[str] = list(state.get("errors") or [])

    # Priority 1: injected prompt_config (e.g. from parent pathway graph)
    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return {"system_prompt": cfg["systemPrompt"], "errors": errors}

    # Priority 2: prompts registry (Neo4j → hardcoded Python constant)
    try:
        from libs.prompts.registry import get_prompt
        text = get_prompt("guidance_rule_extraction", version=1)
        return {"system_prompt": text, "errors": errors}
    except Exception as exc:
        logger.warning("Prompt registry unavailable, using inline fallback: %s", exc)
        errors.append(f"prompt_registry_unavailable: {exc}")
        return {"system_prompt": _FALLBACK_SYSTEM_PROMPT, "errors": errors}


# ── Node 2: extract_criteria ───────────────────────────────────────────────────

def _parse_llm_output(raw: str) -> dict[str, Any] | None:
    """Parse LLM JSON response into {present, absent, action}."""
    try:
        from libs.llm_client.prompt_safety import cap_llm_response
        capped = cap_llm_response(raw, max_chars=2000) or ""
    except ImportError:
        capped = raw[:2000]

    start = capped.find("{")
    end = capped.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(capped[start:end])
        return {
            "present": [str(t) for t in (data.get("present") or [])[:5]],
            "absent":  [str(t) for t in (data.get("absent")  or [])[:5]],
            "action":  str(data["action"]) if data.get("action") else None,
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def extract_criteria(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Run dual-model consensus to extract present/absent criteria and action."""
    errors: list[str] = list(state.get("errors") or [])
    rec = state.get("recommendation") or {}
    system_prompt = state.get("system_prompt") or _FALLBACK_SYSTEM_PROMPT

    verbatim = rec.get("verbatim") or rec.get("title") or ""
    if not verbatim.strip():
        logger.info("Recommendation %s has no verbatim text — skipping", rec.get("id"))
        return {"raw_criteria": None, "errors": errors}

    try:
        from libs.llm_client.prompt_safety import sanitise_for_prompt, INJECTION_GUARD
        safe_verbatim = sanitise_for_prompt(verbatim, max_chars=2000)
        guarded_system = INJECTION_GUARD + system_prompt
    except ImportError:
        safe_verbatim = verbatim[:2000]
        guarded_system = system_prompt

    # Build user message with full context so LLM knows the site of cancer / section
    context_parts = []
    if rec.get("chapter_title"):
        context_parts.append(f"Chapter: {rec['chapter_title']}")
    if rec.get("section_title"):
        context_parts.append(f"Section: {rec['section_title']}")
    context_parts.append(f"Recommendation {rec.get('title', '')}: {safe_verbatim}")
    context_parts.append(f"Urgency: {rec.get('urgency', 'unspecified')}")
    context_parts.append(f"Strength: {rec.get('strength', 'unspecified')}")

    user_msg = "\n".join(context_parts) + "\n\nExtract the clinical decision criteria as JSON."

    try:
        from libs.llm_client.consensus import run_consensus
        result = run_consensus(
            system_prompt=guarded_system,
            user_msg=user_msg,
            parse_fn=_parse_llm_output,
            fail_verdict=None,
            max_tokens=800,
        )
        if result.verdict is None:
            logger.info("No criteria extracted for recommendation %s", rec.get("id"))
            return {"raw_criteria": None, "errors": errors}
        return {"raw_criteria": result.verdict, "errors": errors}
    except Exception as exc:
        logger.exception("LLM consensus failed for recommendation %s", rec.get("id"))
        errors.append(f"llm_error:{rec.get('id')}:{exc}")
        return {"raw_criteria": None, "errors": errors}


# ── Node 3: code_snomed ────────────────────────────────────────────────────────

def _terminology_search(term: str, semantic_tags: list[str]) -> CriterionResult:
    """Call the Terminology API to find the best SNOMED concept for a plain term.

    Uses GET /terminology/search with semantic_tag filtering.  Returns a
    CriterionResult; ``snomed_concept_id`` is None when no match is found.

    Args:
        term: Plain clinical language term from the LLM.
        semantic_tags: One or more SNOMED semantic tag strings to filter by.

    Returns:
        CriterionResult dict.
    """
    url = f"{_TERMINOLOGY_URL}/terminology/search"
    params: dict[str, Any] = {"q": term, "limit": 3, "semantic_tag": semantic_tags}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            results = resp.json()
    except Exception as exc:
        logger.debug("Terminology API unreachable for %r: %s", term, exc)
        return CriterionResult(
            term=term, snomed_concept_id=None, preferred_term=term, semantic_tag=""
        )

    if not results:
        logger.debug("No SNOMED match for %r (tags=%s)", term, semantic_tags)
        return CriterionResult(
            term=term, snomed_concept_id=None, preferred_term=term, semantic_tag=""
        )

    best = results[0]
    # The search endpoint returns `snomed_concept_id` (from c.id), not `conceptId`
    return CriterionResult(
        term=term,
        snomed_concept_id=str(best.get("snomed_concept_id") or "") or None,
        preferred_term=best.get("term", term),
        semantic_tag=best.get("semantic_tag", ""),
    )


def code_snomed(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Resolve each extracted term to a SNOMED concept via the Terminology API.

    Criteria (present/absent) are looked up with clinical finding/disorder/
    observable entity/situation tags.  The action is looked up with the
    procedure tag.

    Terms that cannot be resolved carry ``snomed_concept_id: null`` — the
    downstream writer skips them when creating the HAS_CRITERIA edge.
    """
    errors: list[str] = list(state.get("errors") or [])
    raw = state.get("raw_criteria")
    if raw is None:
        return {"coded_criteria": None, "errors": errors}

    present_coded: list[CriterionResult] = [
        _terminology_search(t, _CRITERIA_TAGS)
        for t in (raw.get("present") or [])
    ]
    absent_coded: list[CriterionResult] = [
        _terminology_search(t, _CRITERIA_TAGS)
        for t in (raw.get("absent") or [])
    ]
    action_coded: CriterionResult | None = None
    if raw.get("action"):
        action_coded = _terminology_search(raw["action"], _ACTION_TAGS)

    resolved_present = sum(1 for c in present_coded if c.get("snomed_concept_id"))
    resolved_absent  = sum(1 for c in absent_coded  if c.get("snomed_concept_id"))
    logger.info(
        "SNOMED coding: %d/%d present, %d/%d absent, action=%s",
        resolved_present, len(present_coded),
        resolved_absent,  len(absent_coded),
        action_coded.get("snomed_concept_id") if action_coded else "null",
    )

    coded_criteria: CodedCriteria = {
        "present": present_coded,
        "absent":  absent_coded,
        "action":  action_coded,
    }
    return {"coded_criteria": coded_criteria, "errors": errors}


# ── Route ──────────────────────────────────────────────────────────────────────

def _should_code(state: GuidanceRuleExtractionState) -> str:
    """Skip SNOMED coding if LLM produced no criteria."""
    return "code_snomed" if state.get("raw_criteria") is not None else "end"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_guidance_rule_extraction_subgraph() -> CompiledStateGraph:
    """Build the compiled NICE → rule extraction subgraph.

    Graph topology::

        START → resolve_prompt → extract_criteria ──(criteria?)──► code_snomed → END
                                                  └──(none)──────────────────► END
    """
    g = StateGraph(GuidanceRuleExtractionState)
    g.add_node("resolve_prompt",   resolve_prompt)
    g.add_node("extract_criteria", extract_criteria)
    g.add_node("code_snomed",      code_snomed)

    g.add_edge(START, "resolve_prompt")
    g.add_edge("resolve_prompt", "extract_criteria")
    g.add_conditional_edges(
        "extract_criteria",
        _should_code,
        {"code_snomed": "code_snomed", "end": END},
    )
    g.add_edge("code_snomed", END)
    return g.compile()
