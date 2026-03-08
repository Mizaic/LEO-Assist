"""NICE → AppropriatenessRule extraction subgraph.

Three-node LangGraph pipeline that converts a single NICE Recommendation into
structured, SNOMED-coded rule criteria ready to be written to Neo4j.

Nodes
-----
resolve_prompt
    Loads the PromptConfig from Neo4j using a per-guideline priority chain:
      1. ``state["prompt_config"]["systemPrompt"]`` (injected by parent graph)
      2. ``guidance_rule_extraction_{guideline_code}``  (e.g. ``_NG12``)
      3. ``guidance_rule_extraction_default``
      4. ``guidance_rule_extraction``  (backward compat with existing Neo4j nodes)
    Raises no exception on failure — adds an error to state and returns an
    empty system_prompt so downstream nodes skip gracefully.

extract_criteria
    Calls the dual-model consensus pipeline (Haiku + GPT-5 mini, Sonnet
    arbitration) with the resolved prompt.  Parses the LLM output into one
    of two normalised formats (both produce the same ``raw_criteria`` shape):

    *New format* (criteria_groups)::

        {
          "criteria_groups": [
            {"mode": "ALL",  "terms": ["age 40 and over"]},
            {"mode": "ANY",  "terms": ["cough", "dyspnoea", "weight loss"]},
            {"mode": "NOT",  "terms": ["active treatment for lung cancer"]},
          ],
          "action": "fast track referral for suspected lung cancer"
        }

    *Old format* (present / absent) — auto-converted to criteria_groups::

        {"present": [...], "absent": [...], "action": "..."|null}
        →  present  → {"mode": "ALL", "terms": [...]}
        →  absent   → {"mode": "NOT", "terms": [...]}

code_snomed
    For each criterion term calls ``GET /terminology/search`` with the
    appropriate ``semantic_tag`` filter in parallel:

    - criteria terms (ANY/ALL/NOT) → tags: finding, disorder, observable entity, situation
    - action                       → tag: procedure

    Demographic terms (age, sex) are resolved instantly without an API call:
    - Age terms  → ``AppliesToConstraint`` (operator/value/unit) at rule level
    - Sex terms  → hardcoded SNOMED 248152002 / 248153007

State keys consumed by ``guidance_rule_generator.py`` downstream
----------------------------------------------------------------
``coded_criteria`` → dict with keys:
    ``criteria_groups``  list[CriteriaGroupCoded]
    ``action``           ActionResult | None
    ``applies_to``       list[AppliesToConstraint]  (rule-level demographics)

where::

    CriteriaGroupCoded = {
        "mode":        "ANY" | "ALL" | "NOT",
        "coded_terms": list[CriterionResult],
    }
    CriterionResult = {
        "term": str,
        "snomed_concept_id": str | None,
        "preferred_term":   str,
        "semantic_tag":     str,
    }
    AppliesToConstraint = {
        "raw_term":      str,
        "concept_id":    str,     # always "424144002" (age)
        "preferred_term": str,
        "semantic_tag":  str,
        "operator":      str,     # ">=", "<=", ">", "<", "="
        "value":         float,
        "unit":          str,     # "years"
    }
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import time
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class TerminologyAPIError(RuntimeError):
    """Raised when the Terminology API is unreachable or returns an HTTP error.

    This is a HARD failure — callers must not silently continue with
    unresolved criteria.  Any rule whose terms cannot be SNOMED-coded
    must NOT be written to Neo4j.
    """


_TERMINOLOGY_URL = os.getenv("TERMINOLOGY_API_URL", "http://terminology-api:8001")

# Timeout per individual HTTP request to the Terminology API.
# The API runs a CPU-bound BERT embedder.  When the pipeline fires 6 parallel
# requests simultaneously (one per criterion term) on a single-process server,
# each request waits in the worker queue before it can start.
# Default: 15s — enough for queue wait + BERT embed + Lucene search under load.
# Increase via TERMINOLOGY_API_TIMEOUT if the server is very slow (e.g. CPU-only
# with many parallel requests from other services).
_TERMINOLOGY_TIMEOUT = float(os.getenv("TERMINOLOGY_API_TIMEOUT", "15.0"))

# Max parallel HTTP requests to the Terminology API.
# Reducing this slows total coding time but reduces queue pressure on the BERT server.
_TERMINOLOGY_MAX_WORKERS = int(os.getenv("TERMINOLOGY_API_MAX_WORKERS", "6"))

# Retry configuration for transient Terminology API failures.
# Total attempts = 1 initial + TERMINOLOGY_API_RETRIES retries.
# Delay between attempts follows exponential backoff:
#   attempt 1 → TERMINOLOGY_API_RETRY_BASE_DELAY seconds
#   attempt 2 → base * 2
#   attempt N → base * 2^(N-1)  (capped at TERMINOLOGY_API_RETRY_MAX_DELAY)
#
# Only network / 5xx errors are retried.  4xx client errors (bad request) are
# surfaced immediately — retrying them will not help.
_TERMINOLOGY_RETRIES = int(os.getenv("TERMINOLOGY_API_RETRIES", "3"))
_TERMINOLOGY_RETRY_BASE_DELAY = float(os.getenv("TERMINOLOGY_API_RETRY_BASE_DELAY", "1.0"))
_TERMINOLOGY_RETRY_MAX_DELAY = float(os.getenv("TERMINOLOGY_API_RETRY_MAX_DELAY", "8.0"))

_CRITERIA_TAGS = ["finding", "disorder", "observable entity", "situation"]
_ACTION_TAGS = ["procedure"]

# ── Demographic SNOMED constants ───────────────────────────────────────────────

_AGE_CONCEPT_ID = "424144002"
_AGE_PREFERRED_TERM = "Current chronological age (observable entity)"
_AGE_SEMANTIC_TAG = "observable entity"

_SEX_SNOMED: dict[str, tuple[str, str]] = {
    "female":         ("248152002", "Female (finding)"),
    "female sex":     ("248152002", "Female (finding)"),
    "women":          ("248152002", "Female (finding)"),
    "woman":          ("248152002", "Female (finding)"),
    "female patient": ("248152002", "Female (finding)"),
    "male":           ("248153007", "Male (finding)"),
    "male sex":       ("248153007", "Male (finding)"),
    "men":            ("248153007", "Male (finding)"),
    "man":            ("248153007", "Male (finding)"),
    "male patient":   ("248153007", "Male (finding)"),
}

_AGE_RE = re.compile(
    r"aged?\s+(\d+(?:\.\d+)?)\s*(?:years?\s+)?(?:and\s+|or\s+)?"
    r"(over|above|older|more|plus|under|below|younger|less)",
    re.IGNORECASE,
)
_AGE_OPERATOR_MAP = {
    "over":    ">=",
    "above":   ">=",
    "older":   ">=",
    "more":    ">=",
    "plus":    ">=",
    "under":   "<",
    "below":   "<",
    "younger": "<",
    "less":    "<",
}


def _parse_age_constraint(term: str) -> dict[str, Any] | None:
    m = _AGE_RE.search(term)
    if not m:
        return None
    value = float(m.group(1))
    direction = m.group(2).lower()
    operator = _AGE_OPERATOR_MAP.get(direction, ">=")
    return {"operator": operator, "value": value, "unit": "years"}


def _sex_snomed(term: str) -> tuple[str, str] | None:
    return _SEX_SNOMED.get(term.strip().lower())


# ── State ──────────────────────────────────────────────────────────────────────

class CriterionResult(TypedDict, total=False):
    term: str
    snomed_concept_id: str | None
    preferred_term: str
    semantic_tag: str


class AppliesToConstraint(TypedDict, total=False):
    """Demographic criterion evaluated via APPLIES_TO edge (not bitmap)."""
    raw_term: str
    concept_id: str
    preferred_term: str
    semantic_tag: str
    operator: str
    value: float | None
    unit: str | None


class CriteriaGroupCoded(TypedDict, total=False):
    mode: str               # "ANY", "ALL", or "NOT"
    coded_terms: list[CriterionResult]


class CodedCriteria(TypedDict, total=False):
    criteria_groups: list[CriteriaGroupCoded]
    action: CriterionResult | None
    applies_to: list[AppliesToConstraint]


class GuidanceRuleExtractionState(TypedDict, total=False):
    recommendation: dict[str, Any]
    guideline_id: str
    prompt_config: dict[str, Any] | None
    system_prompt: str
    raw_criteria: dict[str, Any] | None
    coded_criteria: CodedCriteria | None
    errors: list[str]
    # Aggregated token counts for all LLM calls made during this run.
    # Keys: input_tokens, output_tokens, cached_input_tokens, llm_calls.
    # Consumed by the rule generator to write AuditEvent nodes.
    llm_tokens: dict[str, int]


# ── Node 1: resolve_prompt ─────────────────────────────────────────────────────

def resolve_prompt(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Load the guidance_rule_extraction PromptConfig from Neo4j.

    Resolution order (all Neo4j — no Python fallback):
      1. Injected ``prompt_config.systemPrompt`` from parent graph
      2. ``guidance_rule_extraction_{guideline_code}``  (e.g. ``_NG12``)
      3. ``guidance_rule_extraction_default``
      4. ``guidance_rule_extraction``  (backward compat with existing nodes)

    On failure logs a critical error and returns ``system_prompt=""`` so
    ``extract_criteria`` skips gracefully rather than crashing the graph.
    """
    errors: list[str] = list(state.get("errors") or [])

    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return {"system_prompt": cfg["systemPrompt"], "errors": errors}

    guideline_id = state.get("guideline_id") or ""
    guideline_code = guideline_id.split(":")[0].strip()  # "NG12" from "NG12:v1:..."

    try:
        from libs.prompts.registry import get_prompt

        candidates = []
        if guideline_code:
            candidates.append(f"guidance_rule_extraction_{guideline_code}")
        candidates += ["guidance_rule_extraction_default", "guidance_rule_extraction"]

        for name in candidates:
            try:
                text = get_prompt(name, version=1)
                logger.debug("Resolved prompt %r for guideline %s", name, guideline_id)
                return {"system_prompt": text, "errors": errors}
            except RuntimeError:
                continue

        # None of the candidates were found in Neo4j
        msg = (
            f"No guidance_rule_extraction prompt found in Neo4j for guideline "
            f"{guideline_id!r}. Run: python -m scripts.seed_prompt_configs"
        )
        logger.error(msg)
        errors.append(f"prompt_missing: {msg}")
        return {"system_prompt": "", "errors": errors}

    except Exception as exc:
        msg = f"prompt_registry_unavailable: {exc}"
        logger.error("Prompt registry error for %s: %s", guideline_id, exc)
        errors.append(msg)
        return {"system_prompt": "", "errors": errors}


# ── Node 2: extract_criteria ───────────────────────────────────────────────────

def _normalise_to_criteria_groups(data: dict) -> dict | None:
    """Normalise both old and new LLM output formats to criteria_groups.

    Old format: ``{"present": [...], "absent": [...], "action": ...}``
    New format: ``{"criteria_groups": [...], "action": ...}``

    Returns the normalised dict or None on parse failure.
    """
    if "criteria_groups" in data:
        groups_raw = data.get("criteria_groups")
        if not isinstance(groups_raw, list):
            return None
        groups = []
        for g in groups_raw:
            if not isinstance(g, dict):
                continue
            mode = str(g.get("mode", "ALL")).upper()
            if mode not in {"ANY", "ALL", "NOT"}:
                mode = "ALL"
            terms = [str(t) for t in (g.get("terms") or [])[:5]]
            if terms:
                groups.append({"mode": mode, "terms": terms})
        return {
            "criteria_groups": groups,
            "action": str(data["action"]) if data.get("action") else None,
        }

    # Old format — convert present→ALL group, absent→NOT group
    present = [str(t) for t in (data.get("present") or [])[:5]]
    absent  = [str(t) for t in (data.get("absent")  or [])[:5]]
    groups = []
    if present:
        groups.append({"mode": "ALL", "terms": present})
    if absent:
        groups.append({"mode": "NOT", "terms": absent})
    return {
        "criteria_groups": groups,
        "action": str(data["action"]) if data.get("action") else None,
    }


def _parse_llm_output(raw: str) -> dict[str, Any] | None:
    """Parse LLM JSON response into normalised criteria_groups format."""
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
        return _normalise_to_criteria_groups(data)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def extract_criteria(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Run dual-model consensus to extract criteria_groups and action."""
    errors: list[str] = list(state.get("errors") or [])
    rec = state.get("recommendation") or {}
    system_prompt = state.get("system_prompt") or ""

    if not system_prompt.strip():
        msg = (
            f"No system prompt for recommendation {rec.get('id')!r} — "
            "extraction BLOCKED. Run: python -m scripts.seed_prompt_configs"
        )
        logger.error(msg)
        errors.append(f"extraction_blocked:no_system_prompt:{rec.get('id')}")
        return {"raw_criteria": None, "errors": errors}

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

    context_parts = []
    if rec.get("chapter_title"):
        context_parts.append(f"Chapter: {rec['chapter_title']}")
    if rec.get("section_title"):
        context_parts.append(f"Section: {rec['section_title']}")
    context_parts.append(f"Recommendation {rec.get('title', '')}: {safe_verbatim}")
    context_parts.append(f"Urgency: {rec.get('urgency', 'unspecified')}")
    context_parts.append(f"Strength: {rec.get('strength', 'unspecified')}")

    user_msg = "\n".join(context_parts) + "\n\nExtract the clinical decision criteria as JSON."

    # Carry forward any tokens already accumulated by an earlier node in this run.
    prior_tokens: dict[str, int] = dict(state.get("llm_tokens") or {})

    def _merge_tokens(result_tokens: dict[str, int]) -> dict[str, int]:
        return {
            "input_tokens":        prior_tokens.get("input_tokens", 0)        + result_tokens.get("input_tokens", 0),
            "output_tokens":       prior_tokens.get("output_tokens", 0)       + result_tokens.get("output_tokens", 0),
            "cached_input_tokens": prior_tokens.get("cached_input_tokens", 0) + result_tokens.get("cached_input_tokens", 0),
            "llm_calls":           prior_tokens.get("llm_calls", 0)           + result_tokens.get("llm_calls", 0),
        }

    try:
        from libs.llm_client.consensus import run_consensus
        result = run_consensus(
            system_prompt=guarded_system,
            user_msg=user_msg,
            parse_fn=_parse_llm_output,
            fail_verdict=None,
            max_tokens=800,
        )
        merged = _merge_tokens({
            "input_tokens":        result.input_tokens,
            "output_tokens":       result.output_tokens,
            "cached_input_tokens": result.cached_input_tokens,
            "llm_calls":           result.llm_calls,
        })
        if result.verdict is None:
            logger.warning(
                "No criteria extracted for recommendation %s — "
                "LLM returned no parseable verdict (both models failed or returned empty output). "
                "Rule will NOT be written.",
                rec.get("id"),
            )
            errors.append(f"extraction_empty:no_llm_verdict:{rec.get('id')}")
            return {"raw_criteria": None, "errors": errors, "llm_tokens": merged}
        return {"raw_criteria": result.verdict, "errors": errors, "llm_tokens": merged}
    except Exception as exc:
        logger.exception("LLM consensus failed for recommendation %s", rec.get("id"))
        errors.append(f"llm_error:{rec.get('id')}:{exc}")
        return {"raw_criteria": None, "errors": errors, "llm_tokens": prior_tokens}


# ── Node 3: code_snomed ────────────────────────────────────────────────────────

def _terminology_search(term: str, semantic_tags: list[str]) -> CriterionResult:
    """Call the Terminology API to find the best SNOMED concept for a plain term.

    Retries transient failures (network errors, timeouts, 5xx responses) up to
    ``_TERMINOLOGY_RETRIES`` times with exponential backoff.  4xx client errors
    are surfaced immediately — retrying will not help.

    Raises:
        TerminologyAPIError: After all retry attempts are exhausted, or on an
            immediate non-retryable error (e.g. HTTP 400/422).  This is a HARD
            failure — the caller (code_snomed) must propagate it so the rule is
            NOT written with unresolved criteria.
    """
    url = f"{_TERMINOLOGY_URL}/terminology/search"
    params: dict[str, Any] = {"q": term, "limit": 3, "semantic_tag": semantic_tags}
    last_exc: Exception | None = None

    for attempt in range(1, _TERMINOLOGY_RETRIES + 1):
        try:
            with httpx.Client(timeout=_TERMINOLOGY_TIMEOUT) as client:
                resp = client.get(url, params=params)

            # 4xx = bad request — do not retry, surface immediately
            if 400 <= resp.status_code < 500:
                raise TerminologyAPIError(
                    f"Terminology API returned {resp.status_code} for term {term!r} "
                    f"(not retrying client errors): {resp.text[:200]}"
                )

            resp.raise_for_status()
            results = resp.json()

            if attempt > 1:
                logger.info(
                    "Terminology API: recovered after %d attempt(s) for term %r.",
                    attempt, term,
                )

            if not results:
                logger.warning(
                    "No SNOMED match found for %r (semantic_tags=%s) — "
                    "term will be unresolved and excluded from the rule criteria.",
                    term, semantic_tags,
                )
                return CriterionResult(
                    term=term, snomed_concept_id=None, preferred_term=term, semantic_tag=""
                )

            best = results[0]
            return CriterionResult(
                term=term,
                snomed_concept_id=str(best.get("snomed_concept_id") or "") or None,
                preferred_term=best.get("term", term),
                semantic_tag=best.get("semantic_tag", ""),
            )

        except TerminologyAPIError:
            raise  # 4xx errors: propagate immediately, no retry

        except Exception as exc:
            last_exc = exc
            if attempt < _TERMINOLOGY_RETRIES:
                delay = min(
                    _TERMINOLOGY_RETRY_BASE_DELAY * (2 ** (attempt - 1)),
                    _TERMINOLOGY_RETRY_MAX_DELAY,
                )
                logger.warning(
                    "Terminology API: attempt %d/%d failed for term %r — "
                    "retrying in %.1fs. url=%s timeout=%.1fs error=%s",
                    attempt, _TERMINOLOGY_RETRIES, term, delay,
                    url, _TERMINOLOGY_TIMEOUT, exc,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Terminology API: all %d attempt(s) EXHAUSTED for term %r. "
                    "url=%s timeout=%.1fs — "
                    "if you see 'timed out' check TERMINOLOGY_API_TIMEOUT (current=%.1fs) "
                    "and TERMINOLOGY_API_MAX_WORKERS (current=%d); the BERT server may be "
                    "overloaded with parallel requests. "
                    "SNOMED coding will be aborted for this recommendation.",
                    _TERMINOLOGY_RETRIES, term,
                    url, _TERMINOLOGY_TIMEOUT,
                    _TERMINOLOGY_TIMEOUT, _TERMINOLOGY_MAX_WORKERS,
                )

    raise TerminologyAPIError(
        f"Terminology API unreachable for term {term!r} after "
        f"{_TERMINOLOGY_RETRIES} attempt(s) (url={url} timeout={_TERMINOLOGY_TIMEOUT}s): {last_exc}"
    ) from last_exc


def _classify_terms(
    terms: list[str],
    label: str,
) -> tuple[list[CriterionResult], list[AppliesToConstraint], list[tuple[str, list[str]]]]:
    """Classify criterion terms without touching the Terminology API.

    Returns:
        coded:     Terms already resolved (sex hardcodes).
        applies_to: Demographic constraints (age APPLIES_TO).
        pending:   List of ``(term, semantic_tags)`` pairs needing an API call.
    """
    coded: list[CriterionResult] = []
    applies_to: list[AppliesToConstraint] = []
    pending: list[tuple[str, list[str]]] = []

    for term in terms:
        age_constraint = _parse_age_constraint(term)
        if age_constraint:
            applies_to.append(AppliesToConstraint(
                raw_term=term,
                concept_id=_AGE_CONCEPT_ID,
                preferred_term=_AGE_PREFERRED_TERM,
                semantic_tag=_AGE_SEMANTIC_TAG,
                operator=age_constraint["operator"],
                value=age_constraint["value"],
                unit=age_constraint["unit"],
            ))
            logger.debug(
                "Age criterion %r (%s) → APPLIES_TO %s %s %s",
                term, label, age_constraint["operator"],
                age_constraint["value"], age_constraint["unit"],
            )
            continue

        sex_match = _sex_snomed(term)
        if sex_match:
            concept_id, preferred_term = sex_match
            coded.append(CriterionResult(
                term=term,
                snomed_concept_id=concept_id,
                preferred_term=preferred_term,
                semantic_tag="finding",
            ))
            logger.debug("Sex criterion %r (%s) → hardcoded SNOMED %s", term, label, concept_id)
            continue

        pending.append((term, _CRITERIA_TAGS))

    return coded, applies_to, pending


def code_snomed(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Resolve each extracted term to a SNOMED concept via the Terminology API.

    Demographic terms (age, sex) are resolved instantly without API calls:
    - Age terms produce rule-level ``AppliesToConstraint`` entries.
    - Sex terms use hardcoded SNOMED codes.

    All remaining clinical terms and the action are looked up in parallel.

    When multiple age constraints are found across groups (dual-age case),
    only the most permissive (minimum) threshold is kept to avoid the
    implicit AND of multiple APPLIES_TO edges creating an impossible gate.
    """
    errors: list[str] = list(state.get("errors") or [])
    raw = state.get("raw_criteria")
    if raw is None:
        return {"coded_criteria": None, "errors": errors}

    try:
        all_applies_to: list[AppliesToConstraint] = []
        coded_groups: list[CriteriaGroupCoded] = []

        # Flat work list for the parallel lookup phase:
        # (group_index, term, semantic_tags)
        work: list[tuple[int, str, list[str]]] = []
        group_coded_terms: list[list[CriterionResult]] = []

        for group in raw.get("criteria_groups") or []:
            mode = str(group.get("mode", "ALL")).upper()
            terms = group.get("terms") or []
            idx = len(coded_groups)
            coded_groups.append({"mode": mode, "coded_terms": []})
            group_coded_terms.append([])

            instant_coded, age_applies_to, pending = _classify_terms(terms, f"group[{idx}]:{mode}")
            group_coded_terms[idx].extend(instant_coded)
            all_applies_to.extend(age_applies_to)

            for term, tags in pending:
                work.append((idx, term, tags))

        # De-duplicate age APPLIES_TO constraints: if multiple age thresholds exist,
        # keep only the minimum (most permissive) to avoid implicit AND logic.
        if len(all_applies_to) > 1:
            age_constraints = [c for c in all_applies_to if c.get("concept_id") == _AGE_CONCEPT_ID]
            other_constraints = [c for c in all_applies_to if c.get("concept_id") != _AGE_CONCEPT_ID]
            if len(age_constraints) > 1:
                # For >= operators, keep the smallest value; for < operators, keep the largest
                gte = [c for c in age_constraints if c.get("operator") in (">=", ">")]
                lt  = [c for c in age_constraints if c.get("operator") in ("<", "<=")]
                deduped = []
                if gte:
                    deduped.append(min(gte, key=lambda c: c.get("value") or 0))
                if lt:
                    deduped.append(max(lt, key=lambda c: c.get("value") or 0))
                if len(deduped) < len(age_constraints):
                    logger.warning(
                        "Multiple age APPLIES_TO constraints reduced to most permissive: %s → %s",
                        [(c.get("operator"), c.get("value")) for c in age_constraints],
                        [(c.get("operator"), c.get("value")) for c in deduped],
                    )
                all_applies_to = deduped + other_constraints

        action_term = raw.get("action") or ""
        action_coded: CriterionResult | None = None

        if work or action_term:
            all_work = [(idx, term, tags) for (idx, term, tags) in work]
            if action_term:
                action_slot = -1
                all_work.append((action_slot, action_term, _ACTION_TAGS))

            max_workers = min(len(all_work), _TERMINOLOGY_MAX_WORKERS)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_slot: dict[concurrent.futures.Future, tuple[int, str]] = {
                    pool.submit(_terminology_search, term, tags): (idx, term)
                    for idx, term, tags in all_work
                }
                for future in concurrent.futures.as_completed(future_to_slot):
                    slot_idx, term_key = future_to_slot[future]
                    try:
                        coded_result: CriterionResult = future.result()
                    except TerminologyAPIError as exc:
                        # Per-term API failure — collect the error but continue so
                        # partial results are still returned to the caller.
                        # The rule generator will see the error and refuse to write
                        # an incomplete rule to Neo4j.
                        logger.error(
                            "Terminology API UNAVAILABLE for term %r — partial results only. "
                            "Error: %s",
                            term_key, exc,
                        )
                        errors.append(f"terminology_api_unavailable:{term_key}:{exc}")
                        coded_result = CriterionResult(
                            term=term_key, snomed_concept_id=None,
                            preferred_term=term_key, semantic_tag="",
                        )
                    if slot_idx == -1:
                        action_coded = coded_result
                    else:
                        group_coded_terms[slot_idx].append(coded_result)

        for idx, group in enumerate(coded_groups):
            group["coded_terms"] = group_coded_terms[idx]

        resolved_total = sum(
            1 for g in coded_groups for c in g.get("coded_terms", [])
            if c.get("snomed_concept_id")
        )
        term_total = sum(len(g.get("coded_terms", [])) for g in coded_groups)
        api_failures = [e for e in errors if "terminology_api_unavailable" in e]
        if api_failures:
            logger.warning(
                "SNOMED coding: %d/%d criteria terms coded (PARTIAL — %d term(s) failed due to "
                "Terminology API unavailability), action=%s, applies_to=%d. "
                "Rule will NOT be written to Neo4j until all terms resolve.",
                resolved_total, term_total, len(api_failures),
                action_coded.get("snomed_concept_id") if action_coded else "null",
                len(all_applies_to),
            )
        else:
            logger.info(
                "SNOMED coding: %d/%d criteria terms coded, action=%s, applies_to=%d",
                resolved_total, term_total,
                action_coded.get("snomed_concept_id") if action_coded else "null",
                len(all_applies_to),
            )

        coded_criteria: CodedCriteria = {
            "criteria_groups": coded_groups,
            "action":          action_coded,
            "applies_to":      all_applies_to,
        }
        return {"coded_criteria": coded_criteria, "errors": errors}

    except Exception as exc:
        logger.exception(
            "SNOMED coding failed unexpectedly — rule will NOT be written to Neo4j."
        )
        errors.append(f"snomed_coding_error:{exc}")
        return {"coded_criteria": None, "errors": errors}


# ── Route ──────────────────────────────────────────────────────────────────────

def _should_code(state: GuidanceRuleExtractionState) -> str:
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
