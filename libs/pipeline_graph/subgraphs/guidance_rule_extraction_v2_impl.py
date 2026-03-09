"""Exact NICE -> guidance rule extraction with verifier-backed SNOMED coding."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.state import CompiledStateGraph
except Exception:  # pragma: no cover - unit tests may run without langgraph installed
    END = "END"
    START = "START"

    class CompiledStateGraph:  # type: ignore[no-redef]
        pass

    class StateGraph:  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs) -> None:
            self._nodes: dict[str, Any] = {}

        def add_node(self, *_args, **_kwargs) -> None:
            return None

        def add_edge(self, *_args, **_kwargs) -> None:
            return None

        def add_conditional_edges(self, *_args, **_kwargs) -> None:
            return None

        def compile(self) -> CompiledStateGraph:
            return CompiledStateGraph()

from libs.terminology.client import ResolvedTerm, TerminologyClient, get_runtime_config

logger = logging.getLogger(__name__)

# Guidance-rule extraction is latency-tolerant compared with interactive flows,
# so default to a less aggressive timeout while still honoring any larger global
# terminology timeout already configured for the process.
_TERMINOLOGY_TIMEOUT = max(
    float(os.getenv("GUIDANCE_RULE_TERMINOLOGY_TIMEOUT", "45.0")),
    float(os.getenv("TERMINOLOGY_API_TIMEOUT", "15.0")),
)
_TERMINOLOGY_RETRIES = int(os.getenv("TERMINOLOGY_API_RETRIES", "3"))

_AGE_RE = re.compile(
    r"aged?\s+(\d+(?:\.\d+)?)\s*(?:years?\s+)?(?:and\s+|or\s+)?"
    r"(over|above|older|more|plus|under|below|younger|less)",
    re.IGNORECASE,
)
_AGE_OPERATOR_MAP = {
    "over": ">=",
    "above": ">=",
    "older": ">=",
    "more": ">=",
    "plus": ">=",
    "under": "<",
    "below": "<",
    "younger": "<",
    "less": "<",
}
_SEX_TERMS = {
    "female": "female",
    "female sex": "female",
    "woman": "female",
    "women": "female",
    "male": "male",
    "male sex": "male",
    "man": "male",
    "men": "male",
}

_VAGUE_SYMPTOM_PHRASE_RE = re.compile(
    r"\b(associated symptoms|symptoms of|additional symptoms|additional signs|additional findings)\b",
    re.IGNORECASE,
)

_INSTRUCTION_ISSUE_TOKENS = (
    "instruction",
    "schema",
    "json",
    "format",
    "parse",
    "invalid",
    "missing field",
)

_NON_CODABLE_CHAPTER_HINTS = (
    "patient information and support",
    "safety netting",
    "diagnostic process",
)

_QUALIFIER_PREFIX_RE = re.compile(
    r"^\s*(unexplained|persistent|recurrent|possible|suspected|new[- ]onset)\s+",
    re.IGNORECASE,
)

_SITE_REFERRAL_RE = re.compile(
    r"suspected\s+([a-z0-9 \-/']+?)\s+cancer",
    re.IGNORECASE,
)


class TerminologyAPIError(RuntimeError):
    """Raised when the Terminology API cannot return candidate lists safely."""


class ResolutionCandidate(TypedDict, total=False):
    concept_id: str | None
    preferred_term: str
    semantic_tag: str
    score: float
    read_code: str | None
    source: str
    search_term: str


class CriterionResult(TypedDict, total=False):
    node_id: str
    term: str
    source_text: str | None
    snomed_concept_id: str | None
    preferred_term: str
    semantic_tag: str
    candidates: list[ResolutionCandidate]
    verification_status: str
    verification_reason: str
    confidence: float


class ActionResult(TypedDict, total=False):
    term: str
    snomed_concept_id: str | None
    preferred_term: str
    semantic_tag: str
    candidates: list[ResolutionCandidate]
    verification_status: str
    verification_reason: str
    confidence: float


class CodedLogicNode(TypedDict, total=False):
    node_id: str
    kind: str
    children: list["CodedLogicNode"]
    min: int
    criterion: CriterionResult
    field: str
    operator: str
    value: float | str | None
    unit: str | None
    raw_term: str


class CodedCriteria(TypedDict, total=False):
    schema_version: int
    logic_tree: CodedLogicNode | None
    action: ActionResult | None
    verifier: dict[str, Any]


class GuidanceRuleExtractionState(TypedDict, total=False):
    recommendation: dict[str, Any]
    guideline_id: str
    prompt_config: dict[str, Any] | None
    system_prompt: str
    few_shot_examples: list[dict[str, Any]]
    raw_criteria: dict[str, Any] | None
    candidate_criteria: dict[str, Any] | None
    coded_criteria: CodedCriteria | None
    errors: list[str]
    llm_tokens: dict[str, int]


def _make_terminology_client(context: str) -> TerminologyClient:
    runtime = get_runtime_config()
    builder_retries = max(0, _TERMINOLOGY_RETRIES - 1)
    service_timeout = float(runtime.get("timeout_seconds") or 0.0)
    service_retries = int(runtime.get("max_retries") or 0)
    logger.info(
        "Guidance rule terminology runtime (%s): service_timeout=%.1fs service_retries=%d "
        "max_terms=%d max_concurrency=%d builder_timeout=%.1fs builder_retries=%d "
        "effective_timeout=%.1fs effective_retries=%d",
        context,
        service_timeout,
        service_retries,
        int(runtime.get("max_terms_per_request") or 0),
        int(runtime.get("max_concurrent_requests") or 0),
        _TERMINOLOGY_TIMEOUT,
        builder_retries,
        max(_TERMINOLOGY_TIMEOUT, service_timeout),
        max(builder_retries, service_retries),
    )
    return TerminologyClient(timeout=_TERMINOLOGY_TIMEOUT, max_retries=builder_retries)


def _dedupe_strs(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _merge_tokens(prior: dict[str, int], result_tokens: dict[str, int]) -> dict[str, int]:
    return {
        "input_tokens": prior.get("input_tokens", 0) + result_tokens.get("input_tokens", 0),
        "output_tokens": prior.get("output_tokens", 0) + result_tokens.get("output_tokens", 0),
        "cached_input_tokens": prior.get("cached_input_tokens", 0) + result_tokens.get("cached_input_tokens", 0),
        "llm_calls": prior.get("llm_calls", 0) + result_tokens.get("llm_calls", 0),
    }


def _parse_age_constraint(term: str) -> dict[str, Any] | None:
    m = _AGE_RE.search(term)
    if not m:
        return None
    value = float(m.group(1))
    direction = m.group(2).lower()
    return {
        "field": "age",
        "operator": _AGE_OPERATOR_MAP.get(direction, ">="),
        "value": value,
        "unit": "years",
        "raw_term": term,
    }


def _parse_sex_constraint(term: str) -> dict[str, Any] | None:
    mapped = _SEX_TERMS.get(term.strip().lower())
    if not mapped:
        return None
    return {"field": "sex", "operator": "=", "value": mapped, "raw_term": term}


def _make_term_obj(value: Any) -> dict[str, Any]:
    def _expanded_search_terms(text: str, base_terms: list[str]) -> list[str]:
        variants = list(base_terms)
        normalized = _QUALIFIER_PREFIX_RE.sub("", text or "").strip()
        if normalized and normalized.lower() != (text or "").strip().lower():
            variants.append(normalized)
        lowered = (text or "").lower()
        if "suggestive of" in lowered:
            variants.append(re.sub(r"\bsuggestive of\b", "", text, flags=re.IGNORECASE).strip())
        if "consistent with" in lowered:
            variants.append(re.sub(r"\bconsistent with\b", "", text, flags=re.IGNORECASE).strip())
        return _dedupe_strs(variants)

    if isinstance(value, dict):
        text = str(value.get("text") or "").strip()
        source_text = value.get("source_text")
        search_terms = _expanded_search_terms(text, [text] + list(value.get("search_terms") or []))
        return {
            "text": text,
            "source_text": str(source_text) if source_text else None,
            "search_terms": search_terms or [text],
            "semantic_hint": str(value.get("semantic_hint")) if value.get("semantic_hint") else None,
            "ambiguity_reason": str(value.get("ambiguity_reason")) if value.get("ambiguity_reason") else None,
        }
    text = str(value or "").strip()
    return {
        "text": text,
        "source_text": None,
        "search_terms": [text] if text else [],
        "semantic_hint": None,
        "ambiguity_reason": None,
    }


def _normalise_action(action: Any) -> dict[str, Any] | None:
    if not action:
        return None
    if isinstance(action, dict):
        text = str(action.get("text") or "").strip()
        if not text:
            return None
        search_terms = _dedupe_strs([text] + list(action.get("search_terms") or []))
        return {"text": text, "search_terms": search_terms or [text]}
    text = str(action).strip()
    if not text:
        return None
    return {"text": text, "search_terms": [text]}


def _expand_action_search_terms(action_text: str, recommendation_text: str) -> list[str]:
    base = _dedupe_strs([action_text])
    if not action_text:
        return base
    variants = list(base)
    lowered = action_text.lower()
    if "referral" in lowered:
        variants.extend(
            [
                "suspected cancer referral",
                "urgent suspected cancer referral",
                "fast track referral suspected cancer",
                "2 week wait suspected cancer referral",
                "2ww suspected cancer referral",
            ]
        )
    site_match = _SITE_REFERRAL_RE.search(action_text) or _SITE_REFERRAL_RE.search(recommendation_text or "")
    if site_match:
        site = " ".join(site_match.group(1).split())
        variants.extend(
            [
                f"fast track referral for suspected {site} cancer",
                f"urgent referral for suspected {site} cancer",
                f"2 week wait referral for suspected {site} cancer",
                f"2ww referral for suspected {site} cancer",
                f"suspected {site} cancer pathway referral",
            ]
        )
    if "mesothelioma" in lowered or "mesothelioma" in (recommendation_text or "").lower():
        variants.extend(
            [
                "fast track referral for suspected mesothelioma",
                "urgent referral for suspected mesothelioma",
                "2 week wait referral for suspected mesothelioma",
            ]
        )
    return _dedupe_strs(variants)


def _make_demographic_or_concept(value: Any) -> dict[str, Any]:
    term = _make_term_obj(value)
    age = _parse_age_constraint(term["text"])
    if age:
        return {"kind": "demographic", **age}
    sex = _parse_sex_constraint(term["text"])
    if sex:
        return {"kind": "demographic", **sex}
    return {"kind": "concept", "term": term}


def _logic_group_from_terms(mode: str, terms: list[Any]) -> dict[str, Any] | None:
    leaves = [_make_demographic_or_concept(t) for t in terms if str(t).strip()]
    if not leaves:
        return None
    mode = str(mode or "ALL").upper()
    if mode == "ANY":
        return {"kind": "OR", "children": leaves}
    if mode == "NOT":
        return {"kind": "NOT", "children": [{"kind": "OR", "children": leaves}]}
    return {"kind": "AND", "children": leaves}


def _assign_node_ids(node: dict[str, Any] | None, prefix: str = "n") -> dict[str, Any] | None:
    if node is None:
        return None
    counter = {"i": 0}

    def _walk(cur: dict[str, Any]) -> dict[str, Any]:
        counter["i"] += 1
        out = dict(cur)
        out.setdefault("node_id", f"{prefix}{counter['i']}")
        if out.get("kind") in {"AND", "OR", "NOT", "AT_LEAST"}:
            out["children"] = [_walk(dict(c)) for c in (out.get("children") or []) if isinstance(c, dict)]
        return out

    return _walk(node)


def _normalise_logic_node(node: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(node.get("kind") or "").upper()
    if kind in {"AND", "OR", "NOT"}:
        children = []
        for child in node.get("children") or []:
            if isinstance(child, dict):
                norm = _normalise_logic_node(child)
                if norm:
                    children.append(norm)
        if not children:
            return None
        return {"kind": kind, "children": children}
    if kind == "AT_LEAST":
        children = []
        for child in node.get("children") or []:
            if isinstance(child, dict):
                norm = _normalise_logic_node(child)
                if norm:
                    children.append(norm)
        min_val = int(node.get("min") or 1)
        if not children:
            return None
        return {"kind": "AT_LEAST", "min": max(1, min_val), "children": children}
    if kind == "DEMOGRAPHIC":
        field = str(node.get("field") or "").lower()
        if field not in {"age", "sex"}:
            return None
        out = {
            "kind": "demographic",
            "field": field,
            "operator": str(node.get("operator") or "="),
            "value": node.get("value"),
            "unit": node.get("unit"),
            "raw_term": str(node.get("raw_term") or ""),
        }
        if field == "age" and out["value"] is not None:
            out["value"] = float(out["value"])
        return out
    if kind == "CONCEPT":
        return {"kind": "concept", "term": _make_term_obj(node.get("term") or node)}
    return None


def _normalise_to_logic_tree(data: dict[str, Any]) -> dict[str, Any] | None:
    if "logic_tree" in data:
        logic_tree_raw = data.get("logic_tree")
        logic_tree = None
        if isinstance(logic_tree_raw, dict):
            logic_tree = _normalise_logic_node(logic_tree_raw)
            logic_tree = _assign_node_ids(logic_tree)
        return {
            "schema_version": 2,
            "logic_tree": logic_tree,
            "action": _normalise_action(data.get("action")),
        }

    if "criteria_groups" in data:
        groups = []
        for group in data.get("criteria_groups") or []:
            if not isinstance(group, dict):
                continue
            logic = _logic_group_from_terms(str(group.get("mode") or "ALL"), list(group.get("terms") or []))
            if logic:
                groups.append(logic)
        logic_tree = {"kind": "AND", "children": groups} if groups else None
        logic_tree = _assign_node_ids(logic_tree)
        return {
            "schema_version": 2,
            "logic_tree": logic_tree,
            "action": _normalise_action(data.get("action")),
        }

    present = list(data.get("present") or [])
    absent = list(data.get("absent") or [])
    groups = []
    if present:
        logic = _logic_group_from_terms("ALL", present)
        if logic:
            groups.append(logic)
    if absent:
        logic = _logic_group_from_terms("NOT", absent)
        if logic:
            groups.append(logic)
    logic_tree = {"kind": "AND", "children": groups} if groups else None
    logic_tree = _assign_node_ids(logic_tree)
    return {
        "schema_version": 2,
        "logic_tree": logic_tree,
        "action": _normalise_action(data.get("action")),
    }


def _parse_json_object(raw: str, *, max_chars: int = 12000) -> dict[str, Any] | None:
    try:
        from libs.llm_client.prompt_safety import cap_llm_response

        capped = cap_llm_response(raw, max_chars=max_chars) or ""
    except ImportError:
        capped = raw[:max_chars]

    start = capped.find("{")
    end = capped.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(capped[start:end])
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def _parse_llm_output(raw: str) -> dict[str, Any] | None:
    data = _parse_json_object(raw, max_chars=12000)
    if data is None:
        return None
    return _normalise_to_logic_tree(data)


def _parse_verifier_output(raw: str) -> dict[str, Any] | None:
    return _parse_json_object(raw, max_chars=16000)


def _looks_like_vague_symptom_clause(text: str) -> bool:
    return bool(_VAGUE_SYMPTOM_PHRASE_RE.search(text or ""))


def _has_instruction_issue(verifier_result: dict[str, Any] | None) -> bool:
    if not verifier_result:
        return False
    reasons: list[str] = []
    if verifier_result.get("reason"):
        reasons.append(str(verifier_result.get("reason")))
    for item in verifier_result.get("leaf_decisions") or []:
        if isinstance(item, dict) and item.get("reason"):
            reasons.append(str(item.get("reason")))
    action_decision = verifier_result.get("action_decision") or {}
    if isinstance(action_decision, dict) and action_decision.get("reason"):
        reasons.append(str(action_decision.get("reason")))
    haystack = " ".join(reasons).lower()
    return any(token in haystack for token in _INSTRUCTION_ISSUE_TOKENS)


def _is_non_codable_service_recommendation(rec: dict[str, Any]) -> bool:
    chapter = str(rec.get("chapter_title") or "").lower()
    section = str(rec.get("section_title") or "").lower()
    title_blob = f"{chapter} {section}"
    return any(hint in title_blob for hint in _NON_CODABLE_CHAPTER_HINTS)


def resolve_prompt(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Load extraction prompt and few-shot examples from Neo4j."""
    errors: list[str] = list(state.get("errors") or [])
    rec = state.get("recommendation") or {}
    if _is_non_codable_service_recommendation(rec):
        # Non-codable service/process guidance short-circuits in extract_criteria;
        # avoid adding noisy prompt_missing errors for this path.
        return {"system_prompt": "", "few_shot_examples": [], "errors": errors}
    cfg = state.get("prompt_config") or {}
    if cfg.get("systemPrompt"):
        return {
            "system_prompt": cfg["systemPrompt"],
            "few_shot_examples": list(cfg.get("fewShotExamples") or []),
            "errors": errors,
        }

    guideline_id = state.get("guideline_id") or ""
    guideline_code = guideline_id.split(":")[0].strip()
    try:
        from libs.prompts.registry import get_prompt_with_few_shot

        candidates = []
        if guideline_code:
            candidates.append(f"guidance_rule_extraction_{guideline_code}")
        candidates += ["guidance_rule_extraction_default", "guidance_rule_extraction"]
        for name in candidates:
            try:
                text, examples = get_prompt_with_few_shot(name, version=1)
                logger.debug("Resolved prompt %r for guideline %s", name, guideline_id)
                return {"system_prompt": text, "few_shot_examples": examples, "errors": errors}
            except RuntimeError:
                continue
        msg = (
            f"No guidance_rule_extraction prompt found in Neo4j for guideline "
            f"{guideline_id!r}. Run: python -m scripts.seed_prompt_configs"
        )
        logger.error(msg)
        errors.append(f"prompt_missing: {msg}")
        return {"system_prompt": "", "few_shot_examples": [], "errors": errors}
    except Exception as exc:
        msg = f"prompt_registry_unavailable: {exc}"
        logger.error("Prompt registry error for %s: %s", guideline_id, exc)
        errors.append(msg)
        return {"system_prompt": "", "few_shot_examples": [], "errors": errors}


def _few_shot_block(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return ""
    blocks: list[str] = []
    for ex in examples[:4]:
        blocks.append(
            "Example input:\n"
            f"{str(ex.get('input') or '').strip()}\n\n"
            "Example output:\n"
            f"{str(ex.get('output') or '').strip()}"
        )
    return "\n\n".join(blocks)


def extract_criteria(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Run dual-model consensus to extract an exact logic tree."""
    errors: list[str] = list(state.get("errors") or [])
    rec = state.get("recommendation") or {}
    system_prompt = state.get("system_prompt") or ""
    few_shot_examples = list(state.get("few_shot_examples") or [])
    prior_tokens: dict[str, int] = dict(state.get("llm_tokens") or {})
    if _is_non_codable_service_recommendation(rec):
        logger.info(
            "Recommendation %s appears non-codable service/process guidance; marking no_rule_expected.",
            rec.get("id"),
        )
        return {
            "raw_criteria": {
                "schema_version": 2,
                "logic_tree": None,
                "action": None,
                "no_rule_expected": True,
                "reason": "non_codable_service_recommendation",
            },
            "errors": errors,
            "llm_tokens": prior_tokens,
        }

    if not system_prompt.strip():
        msg = (
            f"No system prompt for recommendation {rec.get('id')!r} — "
            "extraction BLOCKED. Run: python -m scripts.seed_prompt_configs"
        )
        logger.error(msg)
        errors.append(f"extraction_blocked:no_system_prompt:{rec.get('id')}")
        return {"raw_criteria": None, "errors": errors, "llm_tokens": prior_tokens}

    verbatim = rec.get("verbatim") or rec.get("title") or ""
    if not verbatim.strip():
        logger.info("Recommendation %s has no verbatim text — skipping", rec.get("id"))
        return {"raw_criteria": None, "errors": errors, "llm_tokens": prior_tokens}

    try:
        from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt

        safe_verbatim = sanitise_for_prompt(verbatim, max_chars=2500)
        guarded_system = INJECTION_GUARD + system_prompt
    except ImportError:
        safe_verbatim = verbatim[:2500]
        guarded_system = system_prompt

    context_parts = []
    if rec.get("chapter_title"):
        context_parts.append(f"Chapter: {rec['chapter_title']}")
    if rec.get("section_title"):
        context_parts.append(f"Section: {rec['section_title']}")
    context_parts.append(f"Recommendation {rec.get('title', '')}: {safe_verbatim}")
    context_parts.append(f"Urgency: {rec.get('urgency', 'unspecified')}")
    context_parts.append(f"Strength: {rec.get('strength', 'unspecified')}")
    examples_block = _few_shot_block(few_shot_examples)
    if examples_block:
        context_parts.append("\nExamples:\n" + examples_block)
    context_parts.append(
        "Extract the exact patient-level logic as JSON. "
        "Preserve OR branches, AND branches, threshold logic such as '2 or more', "
        "and demographic constraints exactly. Do not approximate."
    )
    if _looks_like_vague_symptom_clause(safe_verbatim):
        context_parts.append(
            "This recommendation contains vague symptom-family wording. "
            "Expand it into specific patient-presenting symptom/sign terms that are "
            "clinically plausible from this exact recommendation, and include broad "
            "search_terms for each concept."
        )
    user_msg = "\n".join(context_parts)

    try:
        from libs.llm_client.consensus import run_consensus

        merged = dict(prior_tokens)
        attempt_msgs = [
            user_msg,
            user_msg
            + "\n\nSTRICT OUTPUT REMINDER: return ONLY one valid JSON object matching the required schema.",
        ]
        for attempt, attempt_msg in enumerate(attempt_msgs):
            result = run_consensus(
                system_prompt=guarded_system,
                user_msg=attempt_msg,
                parse_fn=_parse_llm_output,
                fail_verdict=None,
                max_tokens=1400,
            )
            merged = _merge_tokens(
                merged,
                {
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cached_input_tokens": result.cached_input_tokens,
                    "llm_calls": result.llm_calls,
                },
            )
            if result.verdict is not None:
                verdict = dict(result.verdict)
                action = verdict.get("action")
                if isinstance(action, dict):
                    action["search_terms"] = _expand_action_search_terms(
                        str(action.get("text") or ""),
                        safe_verbatim,
                    )
                    verdict["action"] = action
                return {"raw_criteria": verdict, "errors": errors, "llm_tokens": merged}
            if attempt == 0:
                logger.warning(
                    "No parseable extraction verdict for %s on first attempt; retrying with strict JSON reminder.",
                    rec.get("id"),
                )
                continue
        logger.warning(
            "No criteria extracted for recommendation %s — "
            "LLM returned no parseable verdict after retry. Rule will NOT be written.",
            rec.get("id"),
        )
        errors.append(f"extraction_empty:no_llm_verdict:{rec.get('id')}")
        return {"raw_criteria": None, "errors": errors, "llm_tokens": merged}
    except Exception as exc:
        logger.exception("LLM consensus failed for recommendation %s", rec.get("id"))
        errors.append(f"llm_error:{rec.get('id')}:{exc}")
        return {"raw_criteria": None, "errors": errors, "llm_tokens": prior_tokens}


def _collect_concept_targets(node: dict[str, Any] | None, out: dict[str, dict[str, Any]]) -> None:
    if not node:
        return
    kind = node.get("kind")
    if kind == "concept":
        out[node["node_id"]] = dict(node.get("term") or {})
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_concept_targets(child, out)


def _merge_candidates(
    targets: dict[str, dict[str, Any]],
    resolved: dict[str, list[ResolvedTerm]],
) -> dict[str, list[ResolutionCandidate]]:
    merged: dict[str, list[ResolutionCandidate]] = {}
    for node_id, term in targets.items():
        candidates_by_id: dict[str, ResolutionCandidate] = {}
        for search_term in _dedupe_strs(list(term.get("search_terms") or []) + [term.get("text", "")]):
            for cand in resolved.get(search_term, []):
                key = str(cand.concept_id or cand.term or search_term)
                candidate: ResolutionCandidate = {
                    "concept_id": cand.concept_id,
                    "preferred_term": str(cand.term or search_term),
                    "semantic_tag": str(cand.semantic_tag or ""),
                    "score": float(cand.score or 0.0),
                    "read_code": cand.read_code,
                    "source": str(cand.raw.get("source") or "hybrid"),
                    "search_term": search_term,
                }
                existing = candidates_by_id.get(key)
                if existing is None or candidate["score"] > float(existing.get("score") or 0.0):
                    candidates_by_id[key] = candidate
        merged[node_id] = sorted(
            candidates_by_id.values(),
            key=lambda c: float(c.get("score") or 0.0),
            reverse=True,
        )[:5]
    return merged


def _resolve_candidate_lists(
    logic_tree: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> tuple[dict[str, list[ResolutionCandidate]], list[ResolutionCandidate]]:
    targets: dict[str, dict[str, Any]] = {}
    _collect_concept_targets(logic_tree, targets)
    action_targets: dict[str, dict[str, Any]] = {}
    if action:
        action_targets["action"] = {"text": action["text"], "search_terms": list(action.get("search_terms") or [action["text"]])}

    all_terms = []
    for term in list(targets.values()) + list(action_targets.values()):
        all_terms.extend(_dedupe_strs(list(term.get("search_terms") or []) + [term.get("text", "")]))
    unique_terms = _dedupe_strs(all_terms)
    if not unique_terms:
        return {}, []

    expected_tags = {st: "procedure" for st in action_targets.get("action", {}).get("search_terms", [])}
    if action_targets.get("action"):
        expected_tags[action_targets["action"]["text"]] = "procedure"

    client = _make_terminology_client("initial_resolve")
    resolved = client.resolve(unique_terms, expected_tags=expected_tags or None)
    if not resolved:
        raise TerminologyAPIError("Terminology resolve returned no candidates for the recommendation")

    merged = _merge_candidates(targets, resolved)
    action_candidates = _merge_candidates(action_targets, resolved).get("action", [])
    return merged, action_candidates


def _annotate_candidate_tree(
    node: dict[str, Any] | None,
    candidate_map: dict[str, list[ResolutionCandidate]],
) -> dict[str, Any] | None:
    if not node:
        return None
    out = dict(node)
    if out.get("kind") == "concept":
        term = dict(out.get("term") or {})
        out["criterion"] = {
            "node_id": out.get("node_id", ""),
            "term": term.get("text", ""),
            "source_text": term.get("source_text"),
            "candidates": candidate_map.get(out.get("node_id", ""), []),
            "snomed_concept_id": None,
            "preferred_term": term.get("text", ""),
            "semantic_tag": "",
            "verification_status": "pending",
            "verification_reason": "",
            "confidence": 0.0,
        }
        out.pop("term", None)
        return out
    out["children"] = [
        c for c in (_annotate_candidate_tree(child, candidate_map) for child in (out.get("children") or []))
        if c is not None
    ]
    return out


def code_snomed(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Resolve all concept leaves via batched /terminology/resolve."""
    errors: list[str] = list(state.get("errors") or [])
    raw = state.get("raw_criteria")
    if raw is None:
        return {"candidate_criteria": None, "errors": errors}
    if bool(raw.get("no_rule_expected")):
        return {
            "candidate_criteria": {
                "schema_version": 2,
                "logic_tree": None,
                "action": None,
                "no_rule_expected": True,
                "reason": str(raw.get("reason") or "non_codable_service_recommendation"),
            },
            "errors": errors,
        }

    try:
        logic_tree = raw.get("logic_tree")
        action = raw.get("action")
        candidate_map, action_candidates = _resolve_candidate_lists(logic_tree, action)
        candidate_tree = _annotate_candidate_tree(copy.deepcopy(logic_tree), candidate_map)
        action_payload = None
        if action:
            action_payload = {
                "term": action["text"],
                "candidates": action_candidates,
                "snomed_concept_id": None,
                "preferred_term": action["text"],
                "semantic_tag": "",
                "verification_status": "pending",
                "verification_reason": "",
                "confidence": 0.0,
            }

        unresolved = sum(
            1 for candidates in candidate_map.values() if not candidates
        ) + (1 if action and not action_candidates else 0)
        logger.info(
            "Terminology resolve: %d concept leaf/leaves, action_candidates=%d unresolved=%d",
            len(candidate_map),
            len(action_candidates),
            unresolved,
        )
        return {
            "candidate_criteria": {
                "schema_version": 2,
                "logic_tree": candidate_tree,
                "action": action_payload,
            },
            "errors": errors,
        }
    except TerminologyAPIError as exc:
        logger.error("Terminology API UNAVAILABLE for recommendation %s: %s", (state.get("recommendation") or {}).get("id"), exc)
        errors.append(f"terminology_api_unavailable:{exc}")
        return {"candidate_criteria": None, "errors": errors}
    except Exception as exc:
        logger.exception("SNOMED coding failed unexpectedly — rule will NOT be written to Neo4j.")
        errors.append(f"snomed_coding_error:{exc}")
        return {"candidate_criteria": None, "errors": errors}


def _collect_leaf_payloads(node: dict[str, Any] | None, out: list[dict[str, Any]]) -> None:
    if not node:
        return
    if node.get("kind") == "concept":
        criterion = dict(node.get("criterion") or {})
        out.append(
            {
                "node_id": criterion.get("node_id", ""),
                "term": criterion.get("term", ""),
                "source_text": criterion.get("source_text"),
                "candidates": criterion.get("candidates") or [],
            }
        )
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_leaf_payloads(child, out)


def _load_verifier_prompt() -> tuple[str, list[dict[str, Any]]]:
    from libs.prompts.registry import get_prompt_with_few_shot

    candidates = [
        "guidance_rule_code_verifier_default",
        "guidance_rule_code_verifier",
    ]
    for name in candidates:
        try:
            return get_prompt_with_few_shot(name, version=1)
        except RuntimeError:
            continue
    raise RuntimeError(
        "No guidance_rule_code_verifier prompt found in Neo4j. "
        "Run: python -m scripts.seed_prompt_configs"
    )


def _build_verifier_user_msg(
    rec: dict[str, Any],
    raw: dict[str, Any],
    candidate_criteria: dict[str, Any],
    few_shot_examples: list[dict[str, Any]],
) -> str:
    examples_block = _few_shot_block(few_shot_examples)
    leaves: list[dict[str, Any]] = []
    _collect_leaf_payloads(candidate_criteria.get("logic_tree"), leaves)
    payload = {
        "recommendation": {
            "id": rec.get("id"),
            "title": rec.get("title"),
            "chapter_title": rec.get("chapter_title"),
            "section_title": rec.get("section_title"),
            "verbatim": rec.get("verbatim"),
            "urgency": rec.get("urgency"),
            "strength": rec.get("strength"),
        },
        "raw_logic_tree": raw.get("logic_tree"),
        "criteria_leaves": leaves,
        "action": candidate_criteria.get("action"),
    }
    body = json.dumps(payload, ensure_ascii=False)
    if not examples_block:
        return body
    return f"Examples:\n{examples_block}\n\nPayload:\n{body}"


def _candidate_lookup(candidate_criteria: dict[str, Any]) -> tuple[dict[str, dict[str, ResolutionCandidate]], dict[str, ResolutionCandidate]]:
    by_leaf: dict[str, dict[str, ResolutionCandidate]] = {}
    leaves: list[dict[str, Any]] = []
    _collect_leaf_payloads(candidate_criteria.get("logic_tree"), leaves)
    for leaf in leaves:
        by_leaf[leaf["node_id"]] = {
            str(c.get("concept_id") or c.get("preferred_term") or ""): c
            for c in (leaf.get("candidates") or [])
        }
    action_lookup = {
        str(c.get("concept_id") or c.get("preferred_term") or ""): c
        for c in ((candidate_criteria.get("action") or {}).get("candidates") or [])
    }
    return by_leaf, action_lookup


def _apply_leaf_decisions(node: dict[str, Any] | None, decisions: dict[str, dict[str, Any]], candidate_lookup: dict[str, dict[str, ResolutionCandidate]]) -> tuple[dict[str, Any] | None, list[str]]:
    if not node:
        return None, []
    errors: list[str] = []
    out = dict(node)
    if out.get("kind") == "concept":
        criterion = dict(out.get("criterion") or {})
        node_id = str(criterion.get("node_id") or "")
        decision = decisions.get(node_id) or {}
        concept_id = str(decision.get("selected_concept_id") or "")
        candidate = candidate_lookup.get(node_id, {}).get(concept_id)
        status = str(decision.get("status") or "")
        if not concept_id or candidate is None or status != "verified":
            errors.append(f"verifier_unresolved:{node_id}:{decision.get('reason') or 'no approved concept'}")
            return None, errors
        out["criterion"] = {
            "node_id": node_id,
            "term": criterion.get("term", ""),
            "source_text": criterion.get("source_text"),
            "snomed_concept_id": candidate.get("concept_id"),
            "preferred_term": candidate.get("preferred_term", criterion.get("term", "")),
            "semantic_tag": candidate.get("semantic_tag", ""),
            "candidates": criterion.get("candidates") or [],
            "verification_status": "verified",
            "verification_reason": str(decision.get("reason") or ""),
            "confidence": float(decision.get("confidence") or 0.0),
        }
        return out, []
    children = []
    for child in out.get("children") or []:
        resolved_child, child_errors = _apply_leaf_decisions(child, decisions, candidate_lookup)
        errors.extend(child_errors)
        if resolved_child is not None:
            children.append(resolved_child)
    out["children"] = children
    return out, errors


def _rerun_requested_searches(
    candidate_criteria: dict[str, Any],
    verifier_result: dict[str, Any],
) -> dict[str, Any]:
    retry_terms: dict[str, list[str]] = {}
    for item in verifier_result.get("leaf_decisions") or []:
        if str(item.get("status") or "") == "retry_search":
            retry_terms[str(item.get("node_id") or "")] = _dedupe_strs(list(item.get("retry_search_terms") or []))
    action_retry = verifier_result.get("action_decision") or {}
    action_search_terms = _dedupe_strs(list(action_retry.get("retry_search_terms") or [])) if str(action_retry.get("status") or "") == "retry_search" else []
    if not retry_terms and not action_search_terms:
        return candidate_criteria

    all_terms = []
    for terms in retry_terms.values():
        all_terms.extend(terms)
    all_terms.extend(action_search_terms)
    all_terms = _dedupe_strs(all_terms)
    if not all_terms:
        return candidate_criteria
    client = _make_terminology_client("retry_search")
    resolved = client.resolve(all_terms, expected_tags={t: "procedure" for t in action_search_terms} or None)
    if not resolved:
        raise TerminologyAPIError("alternate terminology resolve returned no results")

    updated = copy.deepcopy(candidate_criteria)
    lookup_by_leaf, _ = _candidate_lookup(updated)

    def _inject(node: dict[str, Any] | None) -> None:
        if not node:
            return
        if node.get("kind") == "concept":
            criterion = dict(node.get("criterion") or {})
            node_id = str(criterion.get("node_id") or "")
            extra_terms = retry_terms.get(node_id) or []
            if extra_terms:
                merged = {str(c.get("concept_id") or c.get("preferred_term") or ""): c for c in (criterion.get("candidates") or [])}
                for search_term in extra_terms:
                    for cand in resolved.get(search_term, []):
                        key = str(cand.concept_id or cand.term or search_term)
                        merged[key] = {
                            "concept_id": cand.concept_id,
                            "preferred_term": str(cand.term or search_term),
                            "semantic_tag": str(cand.semantic_tag or ""),
                            "score": float(cand.score or 0.0),
                            "read_code": cand.read_code,
                            "source": str(cand.raw.get("source") or "hybrid"),
                            "search_term": search_term,
                        }
                criterion["candidates"] = sorted(merged.values(), key=lambda c: float(c.get("score") or 0.0), reverse=True)[:5]
                node["criterion"] = criterion
            return
        for child in node.get("children") or []:
            _inject(child)

    _inject(updated.get("logic_tree"))
    action = dict(updated.get("action") or {})
    if action and action_search_terms:
        merged = {str(c.get("concept_id") or c.get("preferred_term") or ""): c for c in (action.get("candidates") or [])}
        for search_term in action_search_terms:
            for cand in resolved.get(search_term, []):
                key = str(cand.concept_id or cand.term or search_term)
                merged[key] = {
                    "concept_id": cand.concept_id,
                    "preferred_term": str(cand.term or search_term),
                    "semantic_tag": str(cand.semantic_tag or ""),
                    "score": float(cand.score or 0.0),
                    "read_code": cand.read_code,
                    "source": str(cand.raw.get("source") or "hybrid"),
                    "search_term": search_term,
                }
        action["candidates"] = sorted(merged.values(), key=lambda c: float(c.get("score") or 0.0), reverse=True)[:5]
        updated["action"] = action
    return updated


def verify_codes(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Always-run verifier pass over terminology candidates."""
    errors: list[str] = list(state.get("errors") or [])
    candidate_criteria = state.get("candidate_criteria")
    raw = state.get("raw_criteria")
    rec = state.get("recommendation") or {}
    prior_tokens: dict[str, int] = dict(state.get("llm_tokens") or {})
    if not candidate_criteria:
        return {"coded_criteria": None, "errors": errors, "llm_tokens": prior_tokens}
    if bool(candidate_criteria.get("no_rule_expected")):
        return {
            "coded_criteria": {
                "schema_version": 2,
                "logic_tree": None,
                "action": None,
                "no_rule_expected": True,
                "reason": str(candidate_criteria.get("reason") or "non_codable_service_recommendation"),
                "verifier": {
                    "overall_status": "no_rule_expected",
                    "reason": str(candidate_criteria.get("reason") or "non_codable_service_recommendation"),
                },
            },
            "errors": errors,
            "llm_tokens": prior_tokens,
        }

    try:
        verifier_prompt, few_shot = _load_verifier_prompt()
    except Exception as exc:
        logger.error("Verifier prompt unavailable: %s", exc)
        errors.append(f"verifier_prompt_missing:{exc}")
        return {"coded_criteria": None, "errors": errors, "llm_tokens": prior_tokens}

    working = copy.deepcopy(candidate_criteria)
    merged_tokens = dict(prior_tokens)
    verifier_result: dict[str, Any] | None = None
    for attempt in range(2):
        try:
            from libs.llm_client.consensus import run_consensus

            verdict = run_consensus(
                system_prompt=verifier_prompt,
                user_msg=_build_verifier_user_msg(rec, raw or {}, working, few_shot),
                parse_fn=_parse_verifier_output,
                fail_verdict=None,
                max_tokens=1400,
            )
            merged_tokens = _merge_tokens(
                merged_tokens,
                {
                    "input_tokens": verdict.input_tokens,
                    "output_tokens": verdict.output_tokens,
                    "cached_input_tokens": verdict.cached_input_tokens,
                    "llm_calls": verdict.llm_calls,
                },
            )
            verifier_result = verdict.verdict
            if verifier_result is None:
                if attempt == 0:
                    continue
                errors.append(f"verifier_empty:{rec.get('id')}")
                return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}
            if str(verifier_result.get("overall_status") or "") == "retry_search" and attempt == 0:
                working = _rerun_requested_searches(working, verifier_result)
                continue
            if str(verifier_result.get("overall_status") or "") == "rejected" and attempt == 0 and _has_instruction_issue(verifier_result):
                logger.warning(
                    "Verifier rejected %s due to likely instruction/schema issue; retrying once.",
                    rec.get("id"),
                )
                continue
            break
        except TerminologyAPIError as exc:
            errors.append(f"terminology_api_unavailable:{exc}")
            return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}
        except Exception as exc:
            logger.exception("Verifier failed for recommendation %s", rec.get("id"))
            errors.append(f"verifier_error:{rec.get('id')}:{exc}")
            return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}

    if verifier_result is None:
        errors.append(f"verifier_empty:{rec.get('id')}")
        return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}

    leaf_lookup, action_lookup = _candidate_lookup(working)
    decisions = {
        str(item.get("node_id") or ""): item
        for item in (verifier_result.get("leaf_decisions") or [])
        if item.get("node_id")
    }
    verified_tree, tree_errors = _apply_leaf_decisions(working.get("logic_tree"), decisions, leaf_lookup)
    errors.extend(tree_errors)

    action_payload = None
    action = working.get("action")
    if action:
        action_decision = verifier_result.get("action_decision") or {}
        action_id = str(action_decision.get("selected_concept_id") or "")
        candidate = action_lookup.get(action_id)
        if str(action_decision.get("status") or "") != "verified" or candidate is None:
            errors.append(f"verifier_unresolved:action:{action_decision.get('reason') or 'no approved action'}")
        else:
            action_payload = {
                "term": action.get("term", ""),
                "snomed_concept_id": candidate.get("concept_id"),
                "preferred_term": candidate.get("preferred_term", action.get("term", "")),
                "semantic_tag": candidate.get("semantic_tag", ""),
                "candidates": action.get("candidates") or [],
                "verification_status": "verified",
                "verification_reason": str(action_decision.get("reason") or ""),
                "confidence": float(action_decision.get("confidence") or 0.0),
            }

    if errors or verified_tree is None or str(verifier_result.get("overall_status") or "") != "verified":
        logger.error(
            "Verifier rejected or left unresolved terms for %s — rule will NOT be written. Errors=%s",
            rec.get("id"), errors,
        )
        return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}

    return {
        "coded_criteria": {
            "schema_version": 2,
            "logic_tree": verified_tree,
            "action": action_payload,
            "verifier": verifier_result,
        },
        "errors": errors,
        "llm_tokens": merged_tokens,
    }


def _should_resolve(state: GuidanceRuleExtractionState) -> str:
    raw = state.get("raw_criteria")
    if not raw:
        return "end"
    return "resolve" if (raw.get("logic_tree") is not None or raw.get("action") or raw.get("no_rule_expected")) else "end"


def _should_verify(state: GuidanceRuleExtractionState) -> str:
    return "verify" if state.get("candidate_criteria") is not None else "end"


def build_guidance_rule_extraction_subgraph() -> CompiledStateGraph:
    """Build the exact guidance extraction subgraph."""
    g = StateGraph(GuidanceRuleExtractionState)
    g.add_node("resolve_prompt", resolve_prompt)
    g.add_node("extract_criteria", extract_criteria)
    g.add_node("code_snomed", code_snomed)
    g.add_node("verify_codes", verify_codes)
    g.add_edge(START, "resolve_prompt")
    g.add_edge("resolve_prompt", "extract_criteria")
    g.add_conditional_edges("extract_criteria", _should_resolve, {"resolve": "code_snomed", "end": END})
    g.add_conditional_edges("code_snomed", _should_verify, {"verify": "verify_codes", "end": END})
    g.add_edge("verify_codes", END)
    return g.compile()
