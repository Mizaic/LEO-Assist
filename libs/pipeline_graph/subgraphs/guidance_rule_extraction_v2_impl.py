"""Exact NICE -> guidance rule extraction with verifier-backed SNOMED coding.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

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

from libs.pipeline_graph.subgraphs.verification import (
    _build_tool_result_block,
    _execute_lookup_snomed,
)

logger = logging.getLogger(__name__)

# Max iterations for SNOMED resolver tool loop (same pattern as verification.py).
_MAX_SNOMED_RESOLVER_ITERATIONS = max(
    1, int(os.getenv("GUIDANCE_SNOMED_RESOLVER_MAX_ITERATIONS", "4"))
)

# Bedrock tool config for guidance SNOMED resolver (lookup_snomed + accept_code).
_ACCEPT_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "concept_id": {"type": "string", "description": "SNOMED concept ID."},
        "preferred_term": {
            "type": "string",
            "description": "Preferred term for the concept.",
        },
        "confidence": {"type": "number", "description": "Confidence 0.0-1.0."},
        "reason": {"type": "string", "description": "Short explanation."},
    },
    "required": ["concept_id", "preferred_term"],
}

_GUIDANCE_SNOMED_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "lookup_snomed",
                "description": (
                    "Look up a clinical term in SNOMED. Use query and optional expected_label (e.g. finding, procedure)."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Term or phrase to look up.",
                            },
                            "expected_label": {
                                "type": "string",
                                "description": "Optional semantic tag.",
                            },
                            "entity_index": {
                                "type": "integer",
                                "description": "Unused; pass 0.",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why lookup is needed.",
                            },
                        },
                        "required": ["query"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "accept_code",
                "description": "Submit the selected SNOMED concept when satisfied.",
                "inputSchema": {"json": _ACCEPT_CODE_INPUT_SCHEMA},
            }
        },
    ],
}

_SEMANTIC_EXPANSION_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "ask_big_for_expansions",
                "description": (
                    "Ask a bigger clinical model for semantically constrained SNOMED search term expansions."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"},
                            "semantic_tag": {"type": "string"},
                            "recommendation_text": {"type": "string"},
                        },
                        "required": ["term", "semantic_tag"],
                    }
                },
            }
        }
    ],
}

_RESOLVE_ACCEPT_SCORE = float(os.getenv("GUIDANCE_RESOLVE_ACCEPT_SCORE", "0.82"))
_RESOLVE_PARTIAL_SCORE = float(os.getenv("GUIDANCE_RESOLVE_PARTIAL_SCORE", "0.65"))

# Guidance-rule extraction is latency-tolerant compared with interactive flows.
# Default 120s: batch /resolve can exceed 45s when the terminology service is
# busy (Neo4j + hybrid scoring) or multiple dry-run rules run back-to-back.
# Override with GUIDANCE_RULE_TERMINOLOGY_TIMEOUT.
_TERMINOLOGY_TIMEOUT = max(
    float(os.getenv("GUIDANCE_RULE_TERMINOLOGY_TIMEOUT", "120.0")),
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

_QUOTED_TEXT_RE = re.compile(r"[\"'`]\s*([^\"'`]{3,120})\s*[\"'`]")

_USC_REFERRAL_CANONICAL: dict[str, str] = {
    "oesophageal": "fast track referral for suspected upper gastrointestinal cancer",
    "stomach": "fast track referral for suspected upper gastrointestinal cancer",
    "gastric": "fast track referral for suspected upper gastrointestinal cancer",
    "anal": "fast track referral for suspected lower gastrointestinal cancer",
    "colorectal": "fast track referral for suspected colorectal cancer",
    "vulval": "fast track referral for suspected gynaecological cancer",
    "vulva": "fast track referral for suspected gynaecological cancer",
    "cervical": "fast track referral for suspected gynaecological cancer",
    "ovarian": "fast track referral for suspected gynaecological cancer",
    "endometrial": "fast track referral for suspected gynaecological cancer",
    "oral": "fast track referral for suspected head and neck cancer",
    "laryngeal": "fast track referral for suspected head and neck cancer",
    "thyroid": "fast track referral for suspected head and neck cancer",
    "nasopharyngeal": "fast track referral for suspected head and neck cancer",
    "sarcoma": "fast track referral for suspected sarcoma",
    "soft tissue": "fast track referral for suspected sarcoma",
    "bone": "fast track referral for suspected sarcoma",
    "myeloma": "fast track referral for suspected haematology malignancy",
    "lymphoma": "fast track referral for suspected haematology malignancy",
    "hodgkin": "fast track referral for suspected haematology malignancy",
    "leukaemia": "fast track referral for suspected haematology malignancy",
    "neuroblastoma": "fast track referral for suspected childrens tumour",
    "retinoblastoma": "fast track referral for suspected childrens tumour",
    "wilms": "fast track referral for suspected childrens tumour",
    "brain": "fast track referral for suspected brain tumour",
    "cns": "fast track referral for suspected brain tumour",
    "lung": "fast track referral for suspected lung cancer",
    "mesothelioma": "fast track referral for suspected lung cancer",
    "breast": "fast track referral for suspected breast cancer",
    "skin": "fast track referral for suspected skin cancer",
    "melanoma": "fast track referral for suspected skin cancer",
    "basal cell": "fast track referral for suspected skin cancer",
    "squamous cell": "fast track referral for suspected skin cancer",
    "bladder": "fast track referral for suspected urological cancer",
    "renal": "fast track referral for suspected urological cancer",
    "prostate": "fast track referral for suspected urological cancer",
    "testicular": "fast track referral for suspected urological cancer",
    "penile": "fast track referral for suspected urological cancer",
    "non-site-specific": "fast track referral for suspected cancer due to non-site-specific symptoms",
}

_ACTION_SITE_ALIASES: dict[str, list[str]] = {
    "brain": ["fast track referral for suspected brain tumour"],
    "bladder": ["fast track referral for suspected urological cancer"],
    "cervical": ["fast track referral for suspected gynaecological cancer"],
    "gynaecological": ["fast track referral for suspected gynaecological cancer"],
    "haematological": ["fast track referral for suspected haematology malignancy"],
    "oral": ["fast track referral for suspected head and neck cancer"],
    "head and neck": ["fast track referral for suspected head and neck cancer"],
    "thyroid": ["fast track referral for suspected head and neck cancer"],
    "pancreatic": ["fast track referral for suspected upper gastrointestinal cancer"],
    "stomach": ["fast track referral for suspected upper gastrointestinal cancer"],
    "oesophageal": ["fast track referral for suspected upper gastrointestinal cancer"],
    "retinoblastoma": ["fast track referral for suspected childrens tumour"],
    "hodgkin": ["fast track referral for suspected haematology malignancy"],
    "mesothelioma": ["fast track referral for suspected lung cancer"],
    "sarcoma": ["fast track referral for suspected sarcoma"],
    "skin": ["fast track referral for suspected skin cancer"],
    "testicular": ["fast track referral for suspected urological cancer"],
    "upper gastrointestinal": [
        "fast track referral for suspected upper gastrointestinal cancer"
    ],
    "urological": ["fast track referral for suspected urological cancer"],
    "vulval": ["fast track referral for suspected gynaecological cancer"],
    "lower gastrointestinal": [
        "fast track referral for suspected lower gastrointestinal cancer"
    ],
    "children": ["fast track referral for suspected childrens tumour"],
    "non-site-specific": [
        "fast track referral for suspected cancer due to non-site-specific symptoms",
        "fast track referral for suspected cancer due to non-site-specific symptoms (procedure)",
        "fast track cancer referral",
    ],
}

_ACTION_SITE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retinoblastoma", ("retinoblastoma",)),
    ("soft_tissue_sarcoma", ("soft tissue sarcoma",)),
    ("bone_sarcoma", ("bone sarcoma",)),
    ("sarcoma", ("sarcoma",)),
    ("mesothelioma", ("mesothelioma",)),
    ("lung", ("lung cancer", "lung tumour", "lung tumor")),
    ("myeloma", ("myeloma", "plasma cell")),
    ("haematological", ("haematological", "hematological", "lymphoma", "hodgkin")),
    (
        "children",
        (
            "children",
            "child",
            "paediatric",
            "pediatric",
            "neuroblastoma",
            "retinoblastoma",
        ),
    ),
    (
        "brain_cns",
        (
            "brain cancer",
            "brain tumour",
            "brain tumor",
            "central nervous system",
            " cns ",
            "brain or cns",
        ),
    ),
    ("vulval", ("vulval", "vulva")),
    ("cervical", ("cervical", "cervix")),
    ("gynaecological", ("gynaecological", "gynecological")),
    # "gall bladder" must be matched before "bladder" to avoid false-positive
    # bladder-cancer-site detection for gallbladder ultrasound actions.
    ("gallbladder", ("gall bladder", "gallbladder")),
    ("bladder", ("bladder",)),
    ("prostate", ("prostate",)),
    ("testicular", ("testicular", "testis")),
    ("urological", ("urological", "urology")),
    ("stomach", ("stomach", "gastric")),
    ("oesophageal", ("oesophageal", "esophageal")),
    (
        "upper_gi",
        ("upper gastrointestinal", "upper gi", "oesophagogastric", "esophagogastric"),
    ),
    ("lower_gi", ("lower gastrointestinal", "lower gi")),
    ("oral", (" oral ", "mouth cancer")),
    ("head_neck", ("head and neck",)),
    ("skin", ("skin cancer", "squamous cell carcinoma", "skin lesion")),
    ("colorectal", ("colorectal", "rectal", "colon", "bowel")),
    ("generic_cancer", ("suspected cancer", "cancer referral", "cancer pathway")),
)

_ACTION_SITE_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "retinoblastoma": ("retinoblastoma", "children", "generic_cancer"),
    "soft_tissue_sarcoma": ("soft_tissue_sarcoma", "sarcoma"),
    "bone_sarcoma": ("bone_sarcoma", "sarcoma"),
    "sarcoma": ("sarcoma", "generic_cancer"),
    "mesothelioma": ("mesothelioma", "lung", "generic_cancer"),
    "lung": ("lung", "mesothelioma", "generic_cancer"),
    "myeloma": ("myeloma", "haematological", "generic_cancer"),
    "haematological": ("haematological", "myeloma", "hodgkin", "generic_cancer"),
    "brain_cns": ("brain_cns", "generic_cancer"),
    "vulval": ("vulval", "gynaecological"),
    "cervical": ("cervical", "gynaecological"),
    "gynaecological": ("gynaecological", "generic_cancer"),
    # Gallbladder is hepatobiliary, not urological -- allow self + upper_gi only.
    "gallbladder": ("gallbladder", "upper_gi"),
    "bladder": ("bladder", "urological"),
    "prostate": ("prostate", "urological"),
    "testicular": ("testicular", "urological"),
    "urological": ("urological", "generic_cancer"),
    "stomach": ("stomach", "upper_gi", "generic_cancer"),
    "oesophageal": ("oesophageal", "upper_gi", "generic_cancer"),
    "upper_gi": ("upper_gi", "generic_cancer"),
    "oral": ("oral", "head_neck"),
    "head_neck": ("head_neck", "generic_cancer"),
    "skin": ("skin", "generic_cancer"),
    "colorectal": ("colorectal", "generic_cancer"),
    "lower_gi": ("lower_gi", "colorectal", "generic_cancer"),
    "children": ("children", "retinoblastoma", "generic_cancer"),
    "generic_cancer": ("generic_cancer",),
}


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
    original_phrase: str | None
    expansion_source: str | None
    expanded_from: list[str] | None
    resolver_turns: int | None
    needs_human_review: bool
    search_history: list[list[str]] | None


class ActionResult(TypedDict, total=False):
    term: str
    snomed_concept_id: str | None
    preferred_term: str
    semantic_tag: str
    candidates: list[ResolutionCandidate]
    verification_status: str
    verification_reason: str
    confidence: float
    original_phrase: str | None
    expansion_source: str | None
    expanded_from: list[str] | None
    resolver_turns: int | None
    needs_human_review: bool
    search_history: list[list[str]] | None


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
    needs_human_review: bool
    hitl_terms: list[dict[str, Any]]


class GuidanceRuleExtractionState(TypedDict, total=False):
    recommendation: dict[str, Any]
    guideline_id: str
    prompt_config: dict[str, Any] | None
    system_prompt: str
    few_shot_examples: list[dict[str, Any]]
    raw_criteria: dict[str, Any] | None
    expanded_criteria: dict[str, Any] | None
    candidate_criteria: dict[str, Any] | None
    agentic_terms: list[dict[str, Any]]
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


_GALLBLADDER_RESOLVER_BOOST: tuple[str, ...] = (
    "enlarged gallbladder",
    "gallbladder enlarged",
    "palpable gallbladder",
    "gallbladder palpable",
    "distended gallbladder",
)


def _gallbladder_resolver_boost(*text_parts: str) -> list[str]:
    """High-recall SNOMED lookup phrases (findings) when text mentions gall bladder."""
    combined = " ".join(p for p in text_parts if p).lower()
    if ("gall" in combined and "bladder" in combined) or "gallbladder" in combined:
        return list(_GALLBLADDER_RESOLVER_BOOST)
    return []


_GALLBLADDER_ACTION_BOOST: tuple[str, ...] = (
    "ultrasound scan of gallbladder",
    "gallbladder ultrasound",
    "ultrasonography of gallbladder",
    "direct access ultrasound of gallbladder",
)


def _gallbladder_action_boost(*text_parts: str) -> list[str]:
    """Inject pinned procedure terms first when action text refers to gall bladder."""
    combined = " ".join(p for p in text_parts if p).lower()
    if ("gall" in combined and "bladder" in combined) or "gallbladder" in combined:
        return list(_GALLBLADDER_ACTION_BOOST)
    return []


def _merge_tokens(
    prior: dict[str, int], result_tokens: dict[str, int]
) -> dict[str, int]:
    return {
        "input_tokens": prior.get("input_tokens", 0)
        + result_tokens.get("input_tokens", 0),
        "output_tokens": prior.get("output_tokens", 0)
        + result_tokens.get("output_tokens", 0),
        "cached_input_tokens": prior.get("cached_input_tokens", 0)
        + result_tokens.get("cached_input_tokens", 0),
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
    def _looks_like_threshold_term(text: str) -> bool:
        t = (text or "").lower()
        return any(
            tok in t
            for tok in (
                "fit",
                "ca125",
                "microgram",
                "iu/ml",
                ">=",
                "<=",
                "threshold",
                "test result",
            )
        )

    def _expanded_search_terms(text: str, base_terms: list[str]) -> list[str]:
        variants = list(base_terms)
        normalized = _QUALIFIER_PREFIX_RE.sub("", text or "").strip()
        if normalized and normalized.lower() != (text or "").strip().lower():
            variants.append(normalized)
        lowered = (text or "").lower()
        if "suggestive of" in lowered:
            variants.append(
                re.sub(r"\bsuggestive of\b", "", text, flags=re.IGNORECASE).strip()
            )
        if "consistent with" in lowered:
            variants.append(
                re.sub(r"\bconsistent with\b", "", text, flags=re.IGNORECASE).strip()
            )
        if _looks_like_threshold_term(text):
            variants.extend(
                [
                    re.sub(r"\s+", " ", text).strip(),
                    "test result above threshold",
                    "test result below threshold",
                    "laboratory result threshold",
                ]
            )
            if "fit" in lowered:
                variants.extend(
                    [
                        "faecal immunochemical test result",
                        "faecal haemoglobin result",
                        "faecal immunochemical test threshold",
                    ]
                )
            if "ca125" in lowered:
                variants.extend(
                    [
                        "serum ca125 measurement",
                        "ca125 result",
                        "ca125 threshold result",
                    ]
                )
        return _dedupe_strs(variants)

    if isinstance(value, dict):
        text = str(value.get("text") or "").strip()
        source_text = value.get("source_text")
        llm_terms = list(value.get("search_terms") or [])
        gb_boost = _gallbladder_resolver_boost(text, str(source_text or ""))
        base_terms = [text] + gb_boost + llm_terms
        search_terms = _expanded_search_terms(text, base_terms)
        return {
            "text": text,
            "source_text": str(source_text) if source_text else None,
            "search_terms": search_terms or [text],
            "semantic_hint": (
                str(value.get("semantic_hint")) if value.get("semantic_hint") else None
            ),
            "ambiguity_reason": (
                str(value.get("ambiguity_reason"))
                if value.get("ambiguity_reason")
                else None
            ),
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


def _expand_action_search_terms(
    action_text: str, recommendation_text: str
) -> list[str]:
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
        if (
            "non-urgent" in lowered
            or "routine" in lowered
            or "routine referral" in lowered
        ):
            variants.extend(
                [
                    "non-urgent referral for suspected cancer",
                    "routine referral for suspected cancer",
                    "routine cancer referral",
                ]
            )
    site_match = _SITE_REFERRAL_RE.search(action_text) or _SITE_REFERRAL_RE.search(
        recommendation_text or ""
    )
    if site_match:
        site = " ".join(site_match.group(1).split())
        variants.extend(
            [
                f"fast track referral for suspected {site} cancer",
                f"urgent referral for suspected {site} cancer",
                f"2 week wait referral for suspected {site} cancer",
                f"2ww referral for suspected {site} cancer",
                f"suspected {site} cancer pathway referral",
                f"non-urgent referral for suspected {site} cancer",
                f"routine referral for suspected {site} cancer",
            ]
        )
    if (
        "mesothelioma" in lowered
        or "mesothelioma" in (recommendation_text or "").lower()
    ):
        variants.extend(
            [
                "fast track referral for suspected mesothelioma",
                "urgent referral for suspected mesothelioma",
                "2 week wait referral for suspected mesothelioma",
            ]
        )
    text_blob = f"{action_text} {recommendation_text}".lower()
    for keyword, canonical in _USC_REFERRAL_CANONICAL.items():
        if keyword in text_blob:
            variants.append(canonical)
    for site_key, aliases in _ACTION_SITE_ALIASES.items():
        if site_key in text_blob:
            variants.extend(aliases)
    if "suspected cancer" in text_blob and not site_match:
        variants.extend(_ACTION_SITE_ALIASES["non-site-specific"])
    return _dedupe_strs(variants)


def _normalise_action_text(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()} "


def _is_referral_text(text: str) -> bool:
    low = _normalise_action_text(text)
    return any(token in low for token in (" referral ", " refer ", " pathway "))


def _requested_action_urgency(rec: dict[str, Any], action_text: str) -> str:
    """Determine the required urgency class for an action.

    IMPORTANT: the recommendation `urgency` field reflects the NICE
    recommendation grade ('routine' = 'consider', 'urgent_2w' = '2WW pathway'),
    NOT the urgency class of the action itself.  Always check the action text
    first so that "fast track referral for suspected X cancer" is never
    downgraded to 'routine' just because the NICE recommendation grade is
    'routine'/'consider'.
    """
    urgency = str(rec.get("urgency") or "").lower()
    # -- Check action text FIRST (most authoritative signal) ----------------
    action_blob = _normalise_action_text(action_text)
    if (
        "fast track" in action_blob
        or "2 week wait" in action_blob
        or "2ww" in action_blob
        or "suspected cancer pathway" in action_blob
    ):
        return "fast_track"
    if (
        "very urgent" in action_blob
        or "48 hour" in action_blob
        or "48 hours" in action_blob
    ):
        return "very_urgent"
    if "urgent" in action_blob and "non urgent" not in action_blob:
        return "urgent"
    if "non urgent" in action_blob or "routine" in action_blob:
        return "routine"
    # -- Fall back to recommendation urgency field (urgency class, not grade) ---
    if urgency == "urgent_2w":
        return "fast_track"
    if urgency in {"very_urgent_48h", "immediate"}:
        return "very_urgent"
    if urgency.startswith("urgent"):
        return "urgent"
    # -- Last resort: scan the full verbatim text (but never let "routine" in
    #    verbatim override an action that hasn't been classified yet) ----------
    verbatim_blob = _normalise_action_text(rec.get("verbatim") or "")
    if "non urgent" in verbatim_blob:
        return "routine"
    return "routine" if _is_referral_text(action_text) else "unspecified"


def _detect_action_site(text: str) -> str | None:
    low = _normalise_action_text(text)
    for site, patterns in _ACTION_SITE_PATTERNS:
        if any(f" {pattern} " in low for pattern in patterns):
            return site
    return None


def _candidate_action_urgency(candidate: ResolutionCandidate) -> str:
    low = _normalise_action_text(str(candidate.get("preferred_term") or ""))
    if "non urgent" in low or "routine" in low:
        return "routine"
    if "very urgent" in low or "48 hour" in low or "48 hours" in low:
        return "very_urgent"
    if (
        "fast track" in low
        or "2 week wait" in low
        or "2ww" in low
        or "suspected cancer pathway" in low
    ):
        return "fast_track"
    if "urgent" in low:
        return "urgent"
    return (
        "routine"
        if _is_referral_text(str(candidate.get("preferred_term") or ""))
        else "unspecified"
    )


def _action_candidate_allowed_site(
    requested_site: str | None, candidate_site: str | None
) -> bool:
    if not requested_site:
        return True
    allowed = _ACTION_SITE_COMPATIBILITY.get(requested_site, (requested_site,))
    return bool(candidate_site and candidate_site in allowed)


def _action_candidate_allowed_urgency(
    requested_urgency: str,
    candidate_urgency: str,
    *,
    is_referral: bool,
) -> bool:
    if not is_referral:
        return True
    if requested_urgency == "routine":
        return candidate_urgency == "routine"
    if requested_urgency == "very_urgent":
        return candidate_urgency == "very_urgent"
    if requested_urgency == "fast_track":
        return candidate_urgency in {"fast_track", "very_urgent"}
    if requested_urgency == "urgent":
        return candidate_urgency in {"urgent", "fast_track", "very_urgent"}
    return candidate_urgency != "routine"


def _select_action_candidate(
    rec: dict[str, Any],
    action_term: str,
    candidates: list[ResolutionCandidate],
    verifier_choice: ResolutionCandidate | None,
) -> tuple[ResolutionCandidate | None, str | None]:
    requested_is_referral = _is_referral_text(action_term)
    # For investigations (e.g. urgent chest X-ray), avoid over-constraining site
    # from chapter/section context which can incorrectly bias toward referrals.
    site_context = (
        f"{action_term} {rec.get('section_title') or ''} {rec.get('chapter_title') or ''} {rec.get('verbatim') or ''}"
        if requested_is_referral
        else action_term
    )
    requested_site = _detect_action_site(site_context)
    requested_urgency = _requested_action_urgency(rec, action_term)

    def _score(candidate: ResolutionCandidate) -> tuple[int, int, float]:
        candidate_site = _detect_action_site(str(candidate.get("preferred_term") or ""))
        candidate_urgency = _candidate_action_urgency(candidate)
        if requested_is_referral != _is_referral_text(
            str(candidate.get("preferred_term") or "")
        ):
            return (-1, -1, -1.0)
        if not _action_candidate_allowed_site(requested_site, candidate_site):
            return (-1, -1, -1.0)
        if not _action_candidate_allowed_urgency(
            requested_urgency,
            candidate_urgency,
            is_referral=requested_is_referral,
        ):
            return (-1, -1, -1.0)
        site_score = 1
        if requested_site and candidate_site == requested_site:
            site_score = 3
        elif requested_site and candidate_site in _ACTION_SITE_COMPATIBILITY.get(
            requested_site, ()
        ):
            site_score = 2
        urgency_score = 1
        if requested_urgency == candidate_urgency:
            urgency_score = 3
        elif requested_urgency == "urgent" and candidate_urgency in {
            "fast_track",
            "very_urgent",
        }:
            urgency_score = 2
        elif requested_urgency == "fast_track" and candidate_urgency == "very_urgent":
            urgency_score = 2
        return (site_score, urgency_score, float(candidate.get("score") or 0.0))

    ranked = sorted(
        candidates,
        key=_score,
        reverse=True,
    )
    best = ranked[0] if ranked and _score(ranked[0])[0] >= 0 else None
    if best is None:
        return None, None
    if verifier_choice and str(verifier_choice.get("concept_id")) == str(
        best.get("concept_id")
    ):
        return best, None
    reason = (
        "Applied deterministic action fallback policy: selected the closest site/urgency-compatible "
        "procedure candidate without changing referral urgency or specialty intent."
    )
    return best, reason


def _infer_expected_tag_for_term_obj(
    term: dict[str, Any], *, is_action: bool = False
) -> str | None:
    hint = str(term.get("semantic_hint") or "").strip().lower()
    if hint in {"finding", "procedure", "disorder", "situation", "observable entity"}:
        return hint
    text = " ".join(
        [
            str(term.get("text") or ""),
            str(term.get("source_text") or ""),
            str(term.get("ambiguity_reason") or ""),
        ]
    ).lower()
    if is_action:
        return "procedure"
    if any(
        tok in text
        for tok in ("fit", "ca125", "threshold", "test result", "microgram", "iu/ml")
    ):
        return "observable entity"
    if "suspected" in text and "cancer" in text:
        return "situation"
    if any(
        tok in text
        for tok in (
            "finding",
            "symptom",
            "sign",
            "pain",
            "lump",
            "mass",
            "bleeding",
            "hoarseness",
        )
    ):
        return "finding"
    if any(
        tok in text
        for tok in (
            "x-ray finding",
            "ultrasound finding",
            "scan finding",
            "imaging finding",
        )
    ):
        return "finding"
    # Keep constraints high-confidence only; over-constraining every leaf to
    # "finding" reduced retrieval recall for mixed and edge-case phrasing.
    return None


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


def _assign_node_ids(
    node: dict[str, Any] | None, prefix: str = "n"
) -> dict[str, Any] | None:
    if node is None:
        return None
    counter = {"i": 0}

    def _walk(cur: dict[str, Any]) -> dict[str, Any]:
        counter["i"] += 1
        out = dict(cur)
        out.setdefault("node_id", f"{prefix}{counter['i']}")
        if out.get("kind") in {"AND", "OR", "NOT", "AT_LEAST"}:
            out["children"] = [
                _walk(dict(c))
                for c in (out.get("children") or [])
                if isinstance(c, dict)
            ]
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
            logic = _logic_group_from_terms(
                str(group.get("mode") or "ALL"), list(group.get("terms") or [])
            )
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


def _classify_leaf_difficulty(text: str) -> str:
    low = (text or "").lower()
    if any(
        tok in low
        for tok in (
            "suggestive of",
            "compatible with",
            "consistent with",
            "raises suspicion",
            "suspicious",
        )
    ):
        return "abstract_phrase"
    if any(
        tok in low
        for tok in (
            "new-onset",
            "new onset",
            "progressive",
            "increasing in size",
            "sub-acute",
            "subacute",
        )
    ):
        return "temporal_modifier"
    if any(
        tok in low
        for tok in (
            "fit",
            "ca125",
            "microgram",
            "iu/ml",
            "threshold",
            ">=",
            "<=",
            "per gram",
        )
    ):
        return "quantitative"
    if any(
        tok in low
        for tok in (
            "results suggest",
            "results of the blood tests",
            "results of blood tests",
            "panel",
            "combination of",
        )
    ):
        return "composite_pattern"
    if any(
        tok in low
        for tok in (
            "lip",
            "oral",
            "vulval",
            "vulva",
            "foreskin",
            "prepuce",
            "testicular",
            "glans",
        )
    ):
        return "narrow_body_site"
    return "concrete"


def _expand_term_variants(text: str, category: str) -> list[str]:
    variants = [text]
    low = (text or "").lower()
    if category == "abstract_phrase":
        variants.extend(
            [
                re.sub(
                    r"\b(suggestive of|compatible with|consistent with|raises suspicion of)\b",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip(),
                f"{text} finding",
                f"{text} symptom",
                f"{text} sign",
            ]
        )
    if category == "narrow_body_site":
        variants.extend(
            [
                text.replace("foreskin", "prepuce"),
                text.replace("vulval", "vulva"),
                text.replace("lip lump", "lump of lip"),
                text.replace("lip lump", "labial mass"),
                text.replace("oral cavity", "mouth"),
            ]
        )
    if category == "temporal_modifier":
        stripped = _QUALIFIER_PREFIX_RE.sub("", text).strip()
        variants.extend([stripped, f"{stripped} finding", f"{stripped} disorder"])
    if category == "quantitative":
        variants.extend(
            [
                "laboratory result threshold",
                "test result above threshold",
                "test result below threshold",
            ]
        )
    if category == "composite_pattern":
        variants.extend([f"{text} finding", f"{text} result", f"suspected {text}"])
    if "chest signs compatible with pleural disease" in low:
        variants.extend(
            [
                "pleural disease signs",
                "signs of pleural effusion",
                "pleural friction rub",
                "dullness to percussion",
                "reduced breath sounds",
            ]
        )
    if "chest x-ray findings suggestive of lung cancer" in low:
        variants.extend(
            [
                "abnormal chest x-ray finding",
                "chest radiograph suspicious finding",
                "lung lesion on chest x-ray",
            ]
        )
    return _dedupe_strs([v for v in variants if str(v or "").strip()])


def _semantic_tag_for_category(category: str) -> str:
    if category == "quantitative":
        return "observable entity"
    if category in {
        "abstract_phrase",
        "composite_pattern",
        "temporal_modifier",
        "narrow_body_site",
    }:
        return "finding"
    return "finding"


def _ask_big_for_semantic_expansions(
    term: str, semantic_tag: str, recommendation_text: str
) -> list[str]:
    """Get constrained expansion suggestions from a big model."""
    from libs.llm_client.factory import create_llm
    from libs.llm_client.prompt_safety import cap_llm_response, sanitise_for_prompt

    system = (
        "You are a clinical terminology assistant. Return JSON only with key `search_terms` "
        "as a list of 3-8 concise SNOMED-searchable phrases. Keep terms clinically faithful. "
        "Do not invent unrelated diagnoses."
    )
    payload = {
        "term": sanitise_for_prompt(term, max_chars=200),
        "semantic_tag": semantic_tag,
        "recommendation_text": sanitise_for_prompt(recommendation_text, max_chars=2000),
    }
    llm = create_llm(tier="big")
    resp = llm.converse(
        system=system,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        json_mode=True,
        max_tokens=500,
        agent_task="guidance_rule_arbitrator",
    )
    parsed = _parse_json_object(
        cap_llm_response(resp.text or "", max_chars=2000), max_chars=2000
    )
    if not isinstance(parsed, dict):
        return []
    terms = parsed.get("search_terms")
    if not isinstance(terms, list):
        return []
    return _dedupe_strs([str(t).strip() for t in terms if str(t).strip()])[:8]


def _run_small_to_big_expansion_tool_loop(
    term: str, semantic_tag: str, recommendation_text: str
) -> list[str]:
    """Use a small model as controller with a tool-call to the big model."""
    from libs.llm_client.factory import create_llm
    from libs.llm_client.prompt_safety import sanitise_for_prompt

    system = (
        "You help expand vague clinical phrases into SNOMED-searchable terms. "
        "Use ask_big_for_expansions for difficult or vague phrases."
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": json.dumps(
                {
                    "term": sanitise_for_prompt(term, max_chars=200),
                    "semantic_tag": semantic_tag,
                    "recommendation_text": sanitise_for_prompt(
                        recommendation_text, max_chars=2000
                    ),
                },
                ensure_ascii=False,
            ),
        }
    ]
    llm = create_llm(tier="small")
    out_terms: list[str] = []
    for _ in range(2):
        resp = llm.converse(
            system=system,
            messages=messages,
            tool_config=_SEMANTIC_EXPANSION_TOOL_CONFIG,
            json_mode=True,
            max_tokens=400,
            agent_task="guidance_semantic_expansion",
        )
        if not resp.tool_uses:
            parsed = _parse_json_object(resp.text or "", max_chars=1500)
            if isinstance(parsed, dict) and isinstance(
                parsed.get("search_terms"), list
            ):
                out_terms.extend(
                    [str(t) for t in parsed["search_terms"] if str(t).strip()]
                )
            break
        assistant_content: list[dict[str, Any]] = []
        if resp.text:
            assistant_content.append({"text": resp.text})
        assistant_content.extend({"toolUse": tu} for tu in resp.tool_uses)
        messages.append({"role": "assistant", "content": assistant_content})
        tool_results: list[dict[str, Any]] = []
        for tu in resp.tool_uses:
            if tu.get("name") != "ask_big_for_expansions":
                tool_results.append(
                    _build_tool_result_block(
                        str(tu.get("toolUseId") or ""),
                        {"ok": False, "error": "unsupported_tool"},
                    )
                )
                continue
            inp = dict(tu.get("input") or {})
            terms = _ask_big_for_semantic_expansions(
                str(inp.get("term") or term),
                str(inp.get("semantic_tag") or semantic_tag),
                str(inp.get("recommendation_text") or recommendation_text),
            )
            out_terms.extend(terms)
            tool_results.append(
                _build_tool_result_block(
                    str(tu.get("toolUseId") or ""),
                    {"ok": True, "search_terms": terms},
                )
            )
        if not tool_results:
            break
        messages.append({"role": "user", "content": tool_results})
    return _dedupe_strs(out_terms)[:8]


def _expand_vague_term_semantically(
    text: str, category: str, recommendation_text: str
) -> list[str]:
    if category == "concrete":
        return []
    semantic_tag = _semantic_tag_for_category(category)
    try:
        return _run_small_to_big_expansion_tool_loop(
            text, semantic_tag, recommendation_text
        )
    except Exception:
        logger.exception("Semantic expansion failed for term %r", text)
        return []


def _expand_leaves_in_logic_tree(
    node: dict[str, Any] | None, recommendation_text: str
) -> None:
    if not node:
        return
    if node.get("kind") == "concept":
        term = dict(node.get("term") or {})
        text = str(term.get("text") or "")
        category = _classify_leaf_difficulty(text)
        expanded = _expand_term_variants(text, category)
        term["search_terms"] = _dedupe_strs(
            list(term.get("search_terms") or []) + expanded
        )
        if category != "concrete":
            term["original_phrase"] = text
            term["expansion_source"] = category
            term["expanded_from"] = expanded
            semantic = _expand_vague_term_semantically(
                text, category, recommendation_text
            )
            if semantic:
                term["search_terms"] = _dedupe_strs(
                    list(term.get("search_terms") or []) + semantic
                )
                term["expanded_from"] = _dedupe_strs(
                    list(term.get("expanded_from") or []) + semantic
                )
                term["expansion_source"] = f"{category}+semantic_llm"
            if not term.get("source_text"):
                term["source_text"] = text
        node["term"] = term
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _expand_leaves_in_logic_tree(child, recommendation_text)


def expand_leaves(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    errors: list[str] = list(state.get("errors") or [])
    raw = copy.deepcopy(state.get("raw_criteria"))
    if not raw:
        return {"expanded_criteria": raw, "errors": errors}
    if bool(raw.get("no_rule_expected")):
        return {"expanded_criteria": raw, "errors": errors}

    recommendation_text = str((state.get("recommendation") or {}).get("verbatim") or "")
    _expand_leaves_in_logic_tree(raw.get("logic_tree"), recommendation_text)
    action = dict(raw.get("action") or {})
    if action:
        action_text = str(action.get("text") or "")
        verbatim = str((state.get("recommendation") or {}).get("verbatim") or "")
        action_terms = _expand_action_search_terms(action_text, verbatim)
        # Gallbladder action boost: inject pinned procedure terms FIRST so resolver
        # turn-1 finds 169250003 before any high-confidence-but-wrong vector hit exits.
        gb_lead = _gallbladder_action_boost(action_text, verbatim)
        action["search_terms"] = _dedupe_strs(
            gb_lead + list(action.get("search_terms") or []) + action_terms
        )
        if action_text:
            action["original_phrase"] = action_text
            action["expansion_source"] = "action_expansion"
            action["expanded_from"] = action_terms
        raw["action"] = action
    return {"expanded_criteria": raw, "errors": errors}


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
        for version in (2, 1):
            for name in candidates:
                try:
                    text, examples = get_prompt_with_few_shot(name, version=version)
                    logger.debug(
                        "Resolved prompt %r v%d for guideline %s",
                        name,
                        version,
                        guideline_id,
                    )
                    return {
                        "system_prompt": text,
                        "few_shot_examples": examples,
                        "errors": errors,
                    }
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
                max_tokens=2500,
                json_mode=True,
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
                has_logic = verdict.get("logic_tree") is not None
                has_action = bool(verdict.get("action"))
                no_rule_expected = bool(verdict.get("no_rule_expected"))
                if (
                    not has_logic
                    and not has_action
                    and not no_rule_expected
                    and attempt == 0
                ):
                    # Normative recommendation produced an empty payload; retry once
                    # with a stricter extraction instruction before failing.
                    logger.warning(
                        "Empty extraction payload for %s on first parseable attempt; retrying with forced criterion reminder.",
                        rec.get("id"),
                    )
                    attempt_msgs[1] = (
                        attempt_msgs[1]
                        + "\n\nThis recommendation MUST include at least one patient-level criterion "
                        "unless it is explicitly a service/process-only recommendation."
                    )
                    continue
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


def _collect_concept_targets(
    node: dict[str, Any] | None, out: dict[str, dict[str, Any]]
) -> None:
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
        for search_term in _dedupe_strs(
            list(term.get("search_terms") or []) + [term.get("text", "")]
        ):
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
                if existing is None or candidate["score"] > float(
                    existing.get("score") or 0.0
                ):
                    candidates_by_id[key] = candidate
        merged[node_id] = sorted(
            candidates_by_id.values(),
            key=lambda c: float(c.get("score") or 0.0),
            reverse=True,
        )[:5]
    return merged


def _resolve_term_with_controller(
    *,
    term_obj: dict[str, Any],
    expected_tag: str | None,
    recommendation_text: str,
    is_action: bool,
) -> dict[str, Any]:
    """Single per-term resolve/search/refine controller with max 3 turns."""
    base_term = str(term_obj.get("text") or "")
    search_terms = _dedupe_strs(list(term_obj.get("search_terms") or []) + [base_term])[
        :12
    ]
    history: list[list[str]] = []
    best: list[ResolutionCandidate] = []
    turns = 0
    for idx in range(1, 4):
        turns = idx
        turn_terms = search_terms[:5]
        if not turn_terms:
            break
        history.append(turn_terms)
        client = _make_terminology_client("per_term_controller")
        tags = {t: expected_tag for t in turn_terms if expected_tag}
        resolved = client.resolve(turn_terms, expected_tags=tags or None)
        current = _flatten_resolved(resolved, turn_terms)
        if current:
            merged = {
                str(c.get("concept_id") or c.get("preferred_term") or ""): c
                for c in (best + current)
            }
            best = sorted(
                merged.values(),
                key=lambda c: float(c.get("score") or 0.0),
                reverse=True,
            )[:8]
            if best and float(best[0].get("score") or 0.0) >= _RESOLVE_ACCEPT_SCORE:
                return {
                    "candidates": best,
                    "resolver_turns": turns,
                    "search_history": history,
                    "needs_human_review": False,
                }
        # Refine via agentic tool loop for unresolved/low-confidence terms.
        agentic = _run_agentic_resolver(base_term, expected_tag, recommendation_text)
        extra = list(agentic.get("best_candidates") or [])
        if extra:
            merged = {
                str(c.get("concept_id") or c.get("preferred_term") or ""): c
                for c in (best + extra)
            }
            best = sorted(
                merged.values(),
                key=lambda c: float(c.get("score") or 0.0),
                reverse=True,
            )[:8]
        for h in agentic.get("search_history") or []:
            if isinstance(h, list) and h:
                history.append([str(x) for x in h if str(x).strip()])
        if best and float(best[0].get("score") or 0.0) >= _RESOLVE_ACCEPT_SCORE:
            return {
                "candidates": best,
                "resolver_turns": turns,
                "search_history": history,
                "needs_human_review": False,
            }
        search_terms = _dedupe_strs(
            search_terms
            + _expand_term_variants(base_term, _classify_leaf_difficulty(base_term))
        )
        if is_action:
            search_terms = _dedupe_strs(
                search_terms
                + _expand_action_search_terms(base_term, recommendation_text)
            )

    best_score = float(best[0].get("score") or 0.0) if best else 0.0
    return {
        "candidates": best,
        "resolver_turns": turns,
        "search_history": history,
        "needs_human_review": not bool(best) or best_score < _RESOLVE_PARTIAL_SCORE,
    }


def _resolve_candidate_lists(
    logic_tree: dict[str, Any] | None,
    action: dict[str, Any] | None,
    recommendation_text: str,
) -> tuple[
    dict[str, list[ResolutionCandidate]],
    list[ResolutionCandidate],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    targets: dict[str, dict[str, Any]] = {}
    _collect_concept_targets(logic_tree, targets)
    action_targets: dict[str, dict[str, Any]] = {}
    if action:
        action_targets["action"] = {
            "text": action["text"],
            "search_terms": list(action.get("search_terms") or [action["text"]]),
        }

    merged: dict[str, list[ResolutionCandidate]] = {}
    leaf_meta: dict[str, dict[str, Any]] = {}
    for node_id, term in targets.items():
        expected_tag = _infer_expected_tag_for_term_obj(term, is_action=False)
        result = _resolve_term_with_controller(
            term_obj=term,
            expected_tag=expected_tag,
            recommendation_text=recommendation_text,
            is_action=False,
        )
        merged[node_id] = list(result.get("candidates") or [])
        leaf_meta[node_id] = {
            "resolver_turns": int(result.get("resolver_turns") or 0),
            "search_history": list(result.get("search_history") or []),
            "needs_human_review": bool(result.get("needs_human_review")),
            "expected_tag": expected_tag,
        }

    action_candidates: list[ResolutionCandidate] = []
    action_meta: dict[str, Any] = {}
    if action_targets.get("action"):
        action_term = action_targets["action"]
        expected_tag = (
            _infer_expected_tag_for_term_obj(action_term, is_action=True) or "procedure"
        )
        result = _resolve_term_with_controller(
            term_obj=action_term,
            expected_tag=expected_tag,
            recommendation_text=recommendation_text,
            is_action=True,
        )
        action_candidates = list(result.get("candidates") or [])
        action_meta = {
            "resolver_turns": int(result.get("resolver_turns") or 0),
            "search_history": list(result.get("search_history") or []),
            "needs_human_review": bool(result.get("needs_human_review")),
            "expected_tag": expected_tag,
        }

    return merged, action_candidates, leaf_meta, action_meta


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
            "original_phrase": term.get("original_phrase"),
            "expansion_source": term.get("expansion_source"),
            "expanded_from": term.get("expanded_from"),
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
        c
        for c in (
            _annotate_candidate_tree(child, candidate_map)
            for child in (out.get("children") or [])
        )
        if c is not None
    ]
    return out


def code_snomed(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    """Resolve all concept leaves via batched /terminology/resolve."""
    errors: list[str] = list(state.get("errors") or [])
    raw = state.get("expanded_criteria") or state.get("raw_criteria")
    if raw is None:
        return {"candidate_criteria": None, "errors": errors}
    if bool(raw.get("no_rule_expected")):
        return {
            "candidate_criteria": {
                "schema_version": 2,
                "logic_tree": None,
                "action": None,
                "no_rule_expected": True,
                "reason": str(
                    raw.get("reason") or "non_codable_service_recommendation"
                ),
            },
            "errors": errors,
        }

    try:
        logic_tree = raw.get("logic_tree")
        action = raw.get("action")
        recommendation_text = str(
            (state.get("recommendation") or {}).get("verbatim") or ""
        )
        candidate_map, action_candidates, leaf_meta, action_meta = (
            _resolve_candidate_lists(
                logic_tree,
                action,
                recommendation_text,
            )
        )
        candidate_tree = _annotate_candidate_tree(
            copy.deepcopy(logic_tree), candidate_map
        )
        hitl_terms: list[dict[str, Any]] = []

        def _annotate_meta(node: dict[str, Any] | None) -> None:
            if not node:
                return
            if node.get("kind") == "concept":
                criterion = dict(node.get("criterion") or {})
                meta = leaf_meta.get(str(criterion.get("node_id") or ""), {})
                criterion["resolver_turns"] = int(meta.get("resolver_turns") or 0)
                criterion["search_history"] = list(meta.get("search_history") or [])
                criterion["needs_human_review"] = bool(meta.get("needs_human_review"))
                if criterion["needs_human_review"]:
                    hitl_terms.append(
                        {
                            "kind": "leaf",
                            "node_id": criterion.get("node_id"),
                            "term": criterion.get("term"),
                            "reason": "per_term_controller_unresolved",
                            "search_history": criterion.get("search_history") or [],
                            "best_candidates": list(criterion.get("candidates") or []),
                        }
                    )
                node["criterion"] = criterion
                return
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    _annotate_meta(child)

        _annotate_meta(candidate_tree)
        action_payload = None
        if action:
            action_payload = {
                "term": action["text"],
                "original_phrase": action.get("original_phrase"),
                "expansion_source": action.get("expansion_source"),
                "expanded_from": action.get("expanded_from"),
                "candidates": action_candidates,
                "snomed_concept_id": None,
                "preferred_term": action["text"],
                "semantic_tag": "",
                "verification_status": "pending",
                "verification_reason": "",
                "confidence": 0.0,
                "resolver_turns": int(action_meta.get("resolver_turns") or 0),
                "search_history": list(action_meta.get("search_history") or []),
                "needs_human_review": bool(action_meta.get("needs_human_review")),
            }
            if bool(action_payload.get("needs_human_review")):
                hitl_terms.append(
                    {
                        "kind": "action",
                        "term": action_payload.get("term"),
                        "reason": "per_term_controller_unresolved",
                        "search_history": action_payload.get("search_history") or [],
                        "best_candidates": list(action_payload.get("candidates") or []),
                    }
                )

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
                "hitl_terms": hitl_terms,
            },
            "errors": errors,
        }
    except TerminologyAPIError as exc:
        logger.error(
            "Terminology API UNAVAILABLE for recommendation %s: %s",
            (state.get("recommendation") or {}).get("id"),
            exc,
        )
        errors.append(f"terminology_api_unavailable:{exc}")
        return {"candidate_criteria": None, "errors": errors}
    except Exception as exc:
        logger.exception(
            "SNOMED coding failed unexpectedly — rule will NOT be written to Neo4j."
        )
        errors.append(f"snomed_coding_error:{exc}")
        return {"candidate_criteria": None, "errors": errors}


def _collect_leaf_payloads(
    node: dict[str, Any] | None, out: list[dict[str, Any]]
) -> None:
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
    for version in (2, 1):
        for name in candidates:
            try:
                return get_prompt_with_few_shot(name, version=version)
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


def _candidate_lookup(
    candidate_criteria: dict[str, Any],
) -> tuple[dict[str, dict[str, ResolutionCandidate]], dict[str, ResolutionCandidate]]:
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


def _apply_leaf_decisions(
    node: dict[str, Any] | None,
    decisions: dict[str, dict[str, Any]],
    candidate_lookup: dict[str, dict[str, ResolutionCandidate]],
) -> tuple[dict[str, Any] | None, list[str]]:
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
            errors.append(
                f"verifier_unresolved:{node_id}:{decision.get('reason') or 'no approved concept'}"
            )
            return None, errors
        out["criterion"] = {
            "node_id": node_id,
            "term": criterion.get("term", ""),
            "source_text": criterion.get("source_text"),
            "original_phrase": criterion.get("original_phrase"),
            "expansion_source": criterion.get("expansion_source"),
            "expanded_from": criterion.get("expanded_from"),
            "snomed_concept_id": candidate.get("concept_id"),
            "preferred_term": candidate.get(
                "preferred_term", criterion.get("term", "")
            ),
            "semantic_tag": candidate.get("semantic_tag", ""),
            "candidates": criterion.get("candidates") or [],
            "verification_status": "verified",
            "verification_reason": str(decision.get("reason") or ""),
            "confidence": float(decision.get("confidence") or 0.0),
            "resolver_turns": criterion.get("resolver_turns"),
            "needs_human_review": bool(criterion.get("needs_human_review")),
            "search_history": criterion.get("search_history"),
        }
        return out, []
    children = []
    for child in out.get("children") or []:
        resolved_child, child_errors = _apply_leaf_decisions(
            child, decisions, candidate_lookup
        )
        errors.extend(child_errors)
        if resolved_child is not None:
            children.append(resolved_child)
    out["children"] = children
    return out, errors


def _rerun_requested_searches(
    candidate_criteria: dict[str, Any],
    verifier_result: dict[str, Any],
) -> dict[str, Any]:
    def _leaf_term_lookup(node: dict[str, Any] | None, out: dict[str, str]) -> None:
        if not node:
            return
        if node.get("kind") == "concept":
            criterion = dict(node.get("criterion") or {})
            out[str(criterion.get("node_id") or "")] = str(criterion.get("term") or "")
            return
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _leaf_term_lookup(child, out)

    def _auto_retry_terms(
        reason: str, base_term: str, expected_tag: str | None
    ) -> list[str]:
        out: list[str] = [base_term]
        low = (reason or "").lower()
        base_low = (base_term or "").lower()
        for m in _QUOTED_TEXT_RE.finditer(reason or ""):
            out.append(m.group(1).strip())
        if expected_tag == "finding":
            out.extend(
                [f"{base_term} finding", f"{base_term} symptom", f"{base_term} sign"]
            )
        if expected_tag == "observable entity":
            out.extend(
                [
                    f"{base_term} result",
                    f"{base_term} measurement",
                    f"{base_term} threshold",
                ]
            )
        if expected_tag == "situation":
            out.extend([f"suspected {base_term}", f"{base_term} suspicious"])
        if "diagnosis" in low and expected_tag == "finding":
            out.append(f"suspicious {base_term} finding")
        if "procedure" in low and expected_tag == "finding":
            out.append(f"{base_term} finding")
        if "threshold" in low or "fit" in low or "ca125" in low:
            out.extend(
                [
                    f"{base_term} result",
                    f"{base_term} above threshold",
                    f"{base_term} below threshold",
                ]
            )
        if "ultrasound" in low and any(
            tok in low
            for tok in ("uncertain", "indeterminate", "equivocal", "inconclusive")
        ):
            out.extend(
                [
                    "indeterminate ultrasound finding",
                    "equivocal ultrasound scan finding",
                    "inconclusive ultrasound result",
                    "uncertain imaging finding",
                    "ultrasound scan abnormality",
                ]
            )
        if any(
            tok in low
            for tok in (
                "clinical concern",
                "clinical suspicion",
                "persistent concern",
                "ongoing clinical concern",
            )
        ):
            out.extend(
                [
                    "clinical suspicion",
                    "persistent clinical concern",
                    "ongoing clinical concern",
                    "clinical concern for malignancy",
                    "suspicion finding",
                ]
            )
        if "progressive" in low and "neurolog" in low:
            out.extend(
                [
                    "progressive neurological deterioration",
                    "progressive neurological decline",
                    "subacute neurological deficit",
                    "progressive central neurological deficit",
                    "focal neurological deficit progressive",
                ]
            )
        if (
            "pleural" in low
            or ("chest signs" in low and "pleural" in low)
            or "pleural disease" in base_low
        ):
            out.extend(
                [
                    "pleural disease signs",
                    "signs of pleural effusion",
                    "pleural friction rub",
                    "dullness to percussion",
                    "reduced breath sounds",
                    "abnormal chest examination findings",
                ]
            )
        if "skin lesion" in low or "squamous cell carcinoma" in low:
            out.extend(
                [
                    "suspicious skin lesion",
                    "skin lesion suspicious for malignancy",
                    "skin lesion finding",
                    "suspected squamous cell carcinoma of skin",
                    "skin lesion suspicious for squamous cell carcinoma",
                ]
            )
        if "cerv" in low:
            out.extend(
                [
                    "abnormal cervix on examination",
                    "cervical lesion",
                    "suspicious cervical lesion",
                    "cervical appearance abnormal",
                    "cervical finding suggestive of malignancy",
                ]
            )
        if "vulv" in low and "bleed" in low:
            out.extend(
                [
                    "vulval bleeding",
                    "bleeding from vulva",
                    "vulvar hemorrhage",
                    "vulval haemorrhage",
                ]
            )
        if "red reflex" in low or "fundal" in low or "leukocoria" in low:
            out.extend(
                [
                    "absent red reflex",
                    "red reflex absent",
                    "leukocoria",
                    "white pupil reflex",
                    "absent fundal red reflex",
                ]
            )
        if "hepatosplen" in low or ("enlarged liver" in low and "spleen" in low):
            out.extend(
                [
                    "hepatosplenomegaly",
                    "hepatosplenomegaly finding",
                    "enlarged liver and spleen finding",
                    "hepatomegaly and splenomegaly finding",
                ]
            )
        if expected_tag == "procedure":
            if any(
                tok in low
                for tok in (
                    "stomach",
                    "gastric",
                    "upper gastrointestinal",
                    "upper gi",
                    "oesophageal",
                )
            ):
                out.extend(
                    [
                        "fast track referral for suspected stomach cancer",
                        "fast track referral for suspected gastric cancer",
                        "fast track referral for suspected upper gastrointestinal cancer",
                        "urgent referral for suspected upper gastrointestinal cancer",
                    ]
                )
            if any(
                tok in low
                for tok in (
                    "vulval",
                    "vulva",
                    "cervical",
                    "cervix",
                    "gynaecological",
                    "gynecological",
                )
            ):
                out.extend(
                    [
                        "fast track referral for suspected gynaecological cancer",
                        "urgent referral for suspected gynaecological cancer",
                    ]
                )
            if "retinoblastoma" in low:
                out.extend(
                    [
                        "fast track referral for suspected retinoblastoma",
                        "fast track cancer referral",
                        "urgent suspected cancer referral",
                    ]
                )
            if "bladder" in low and any(
                tok in low for tok in ("non-urgent", "routine")
            ):
                out.extend(
                    [
                        "non-urgent referral for suspected bladder cancer",
                        "non-urgent referral for suspected urological cancer",
                        "routine referral for suspected bladder cancer",
                        "routine referral for suspected urological cancer",
                    ]
                )
            if "sarcoma" in low:
                out.extend(
                    [
                        "fast track referral for suspected sarcoma",
                        "urgent referral for suspected sarcoma",
                        "fast track referral for suspected soft tissue sarcoma",
                        "fast track referral for suspected bone sarcoma",
                    ]
                )
            if (
                any(
                    tok in low
                    for tok in (
                        "children",
                        "child",
                        "young people",
                        "young person",
                        "paediatric",
                        "pediatric",
                    )
                )
                and "suspected cancer" in low
            ):
                out.extend(
                    [
                        "referral for suspected cancer",
                        "urgent referral for suspected cancer",
                        "referral for suspected malignancy",
                        "urgent referral to paediatric oncology",
                    ]
                )
        return _dedupe_strs(out)

    retry_terms: dict[str, list[str]] = {}
    leaf_reason: dict[str, str] = {}
    for item in verifier_result.get("leaf_decisions") or []:
        if str(item.get("status") or "") == "retry_search":
            node_id = str(item.get("node_id") or "")
            retry_terms[node_id] = _dedupe_strs(
                list(item.get("retry_search_terms") or [])
            )
            leaf_reason[node_id] = str(item.get("reason") or "")
    action_retry = verifier_result.get("action_decision") or {}
    action_search_terms = (
        _dedupe_strs(list(action_retry.get("retry_search_terms") or []))
        if str(action_retry.get("status") or "") == "retry_search"
        else []
    )
    action_reason = str(action_retry.get("reason") or "")
    leaf_terms: dict[str, str] = {}
    _leaf_term_lookup(candidate_criteria.get("logic_tree"), leaf_terms)
    for node_id in list(retry_terms.keys()):
        base = leaf_terms.get(node_id, "")
        expected_tag = _infer_expected_tag_for_term_obj({"text": base}, is_action=False)
        retry_terms[node_id] = _dedupe_strs(
            list(retry_terms.get(node_id) or [])
            + _auto_retry_terms(leaf_reason.get(node_id, ""), base, expected_tag)
        )
    if str(action_retry.get("status") or "") == "retry_search":
        action_base = str((candidate_criteria.get("action") or {}).get("term") or "")
        action_search_terms = _dedupe_strs(
            action_search_terms
            + _expand_action_search_terms(action_base, "")
            + _auto_retry_terms(action_reason, action_base, "procedure")
        )
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
    expected_tags: dict[str, str] = {t: "procedure" for t in action_search_terms}
    for node_id, terms in retry_terms.items():
        base = leaf_terms.get(node_id, "")
        tag = _infer_expected_tag_for_term_obj({"text": base}, is_action=False)
        if not tag:
            continue
        for t in terms:
            expected_tags.setdefault(t, tag)
    resolved = client.resolve(all_terms, expected_tags=expected_tags or None)
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
                merged = {
                    str(c.get("concept_id") or c.get("preferred_term") or ""): c
                    for c in (criterion.get("candidates") or [])
                }
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
                criterion["candidates"] = sorted(
                    merged.values(),
                    key=lambda c: float(c.get("score") or 0.0),
                    reverse=True,
                )[:5]
                node["criterion"] = criterion
            return
        for child in node.get("children") or []:
            _inject(child)

    _inject(updated.get("logic_tree"))
    action = dict(updated.get("action") or {})
    if action and action_search_terms:
        merged = {
            str(c.get("concept_id") or c.get("preferred_term") or ""): c
            for c in (action.get("candidates") or [])
        }
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
        action["candidates"] = sorted(
            merged.values(), key=lambda c: float(c.get("score") or 0.0), reverse=True
        )[:5]
        updated["action"] = action
    return updated


def _needs_agentic_retry(
    candidates: list[ResolutionCandidate], *, threshold: float = 0.8
) -> bool:
    if not candidates:
        return True
    best = max(float(c.get("score") or 0.0) for c in candidates)
    return best < threshold


def _flatten_resolved(
    resolved: dict[str, list[ResolvedTerm]], search_terms: list[str]
) -> list[ResolutionCandidate]:
    candidates: dict[str, ResolutionCandidate] = {}
    for search_term in search_terms:
        for cand in resolved.get(search_term, []):
            key = str(cand.concept_id or cand.term or search_term)
            candidates[key] = {
                "concept_id": cand.concept_id,
                "preferred_term": str(cand.term or search_term),
                "semantic_tag": str(cand.semantic_tag or ""),
                "score": float(cand.score or 0.0),
                "read_code": cand.read_code,
                "source": str(cand.raw.get("source") or "hybrid"),
                "search_term": search_term,
            }
    return sorted(
        candidates.values(), key=lambda c: float(c.get("score") or 0.0), reverse=True
    )[:8]


def _heuristic_agentic_search(
    base_term: str, expected_tag: str | None, recommendation_text: str
) -> dict[str, Any]:
    """Fallback when Bedrock tool loop fails: deterministic multi-turn terminology search."""
    variants = _expand_term_variants(base_term, _classify_leaf_difficulty(base_term))
    if expected_tag == "procedure":
        variants = _dedupe_strs(
            variants + _expand_action_search_terms(base_term, recommendation_text)
        )
    turns = [variants[:5], variants[5:10], variants[10:15]]
    search_history: list[list[str]] = []
    best: list[ResolutionCandidate] = []
    client = _make_terminology_client("agentic_fallback")
    for idx, turn_terms in enumerate(turns, start=1):
        if not turn_terms:
            break
        search_history.append(turn_terms)
        expected_tags = {t: expected_tag for t in turn_terms if expected_tag}
        resolved = client.resolve(turn_terms, expected_tags=expected_tags or None)
        current = _flatten_resolved(resolved, turn_terms)
        if current:
            merged = {
                str(c.get("concept_id") or c.get("preferred_term") or ""): c
                for c in (best + current)
            }
            best = sorted(
                merged.values(),
                key=lambda c: float(c.get("score") or 0.0),
                reverse=True,
            )[:8]
            if not _needs_agentic_retry(best):
                return {
                    "selected": best[0],
                    "needs_human_review": False,
                    "resolver_turns": idx,
                    "best_candidates": best,
                    "search_history": search_history,
                    "reason": "Resolved by iterative terminology search fallback.",
                }
    return {
        "selected": best[0] if best else None,
        "needs_human_review": True,
        "resolver_turns": min(3, len(search_history) or 3),
        "best_candidates": best,
        "search_history": search_history,
        "reason": "No safe match after 3 turns; requires human review.",
    }


def _run_snomed_resolver_tool_loop(
    base_term: str, expected_tag: str | None, recommendation_text: str
) -> dict[str, Any]:
    """Verification-style tool loop: create_llm().converse(tool_config=...) with lookup_snomed + accept_code."""
    from libs.llm_client.factory import create_llm
    from libs.llm_client.prompt_safety import sanitise_for_prompt

    system = (
        "You are a clinical terminology resolver for SNOMED CT. "
        "Use lookup_snomed to search for concepts. If you find a safe match (score >= 0.8), call accept_code. "
        "Try at most 3 lookups, refining the query each time. "
        "If no safe match exists, do NOT call accept_code; respond with a short explanation."
    )
    user_payload = {
        "term": base_term,
        "semantic_tag": expected_tag,
        "recommendation_text": sanitise_for_prompt(recommendation_text, max_chars=4000),
    }
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
    ]

    llm = create_llm(tier="big")
    search_history: list[list[str]] = []
    pool: list[ResolutionCandidate] = []
    accepted: dict[str, Any] | None = None

    for _ in range(_MAX_SNOMED_RESOLVER_ITERATIONS):
        resp = llm.converse(
            system=system,
            messages=messages,
            tool_config=_GUIDANCE_SNOMED_TOOL_CONFIG,
            json_mode=True,
            agent_task="guidance_snomed_resolver",
        )

        if resp.tool_uses:
            assistant_content: list[dict[str, Any]] = []
            if resp.text:
                assistant_content.append({"text": resp.text})
            assistant_content.extend({"toolUse": tu} for tu in resp.tool_uses)
            messages.append({"role": "assistant", "content": assistant_content})

            accept_tool = next(
                (tu for tu in resp.tool_uses if tu.get("name") == "accept_code"), None
            )
            if accept_tool is not None:
                accepted = dict(accept_tool.get("input") or {})
                break

            tool_results: list[dict[str, Any]] = []
            for tu in resp.tool_uses:
                if tu.get("name") != "lookup_snomed":
                    tool_results.append(
                        _build_tool_result_block(
                            str(tu.get("toolUseId") or ""),
                            {
                                "ok": False,
                                "error": f"unsupported_tool:{tu.get('name')}",
                            },
                        )
                    )
                    continue
                inp = dict(tu.get("input") or {})
                inp.setdefault("entity_index", 0)
                payload, _ = _execute_lookup_snomed(inp)
                if payload.get("ok") and payload.get("candidates"):
                    for c in payload["candidates"]:
                        pool.append(
                            {
                                "concept_id": c.get("concept_id"),
                                "preferred_term": c.get("term"),
                                "semantic_tag": c.get("semantic_tag"),
                                "score": c.get("score", 0.0),
                                "read_code": c.get("read_code"),
                                "source": "agentic_tool",
                                "search_term": inp.get("query", ""),
                            }
                        )
                    q = str(inp.get("query") or "").strip()
                    if q:
                        search_history.append([q])
                tool_results.append(
                    _build_tool_result_block(str(tu.get("toolUseId") or ""), payload)
                )

            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})
            continue

        break

    merged = {
        str(c.get("concept_id") or c.get("preferred_term") or ""): c
        for c in pool
        if isinstance(c, dict)
    }
    best = sorted(
        merged.values(), key=lambda c: float(c.get("score") or 0.0), reverse=True
    )[:8]

    if accepted:
        selected = next(
            (
                c
                for c in best
                if str(c.get("concept_id") or "")
                == str(accepted.get("concept_id") or "")
            ),
            best[0] if best else None,
        )
        return {
            "selected": selected,
            "needs_human_review": selected is None,
            "resolver_turns": min(3, max(1, len(search_history))),
            "best_candidates": best,
            "search_history": search_history,
            "reason": str(accepted.get("reason") or "Accepted by agent tool call."),
        }

    if best and not _needs_agentic_retry(best):
        return {
            "selected": best[0],
            "needs_human_review": False,
            "resolver_turns": min(3, max(1, len(search_history))),
            "best_candidates": best,
            "search_history": search_history,
            "reason": "Resolved by agentic search.",
        }

    return {
        "selected": best[0] if best else None,
        "needs_human_review": True,
        "resolver_turns": min(3, max(1, len(search_history))),
        "best_candidates": best,
        "search_history": search_history,
        "reason": "No safe match after tool loop; requires human review.",
    }


def _run_agentic_resolver(
    base_term: str, expected_tag: str | None, recommendation_text: str
) -> dict[str, Any]:
    """Run verification-style SNOMED tool loop; fall back to heuristic search on failure."""
    try:
        return _run_snomed_resolver_tool_loop(
            base_term, expected_tag, recommendation_text
        )
    except Exception:
        logger.exception(
            "Agentic resolver failed for term %r; falling back.", base_term
        )
        return _heuristic_agentic_search(base_term, expected_tag, recommendation_text)


def agentic_resolve(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    errors: list[str] = list(state.get("errors") or [])
    candidate_criteria = copy.deepcopy(state.get("candidate_criteria"))
    if not candidate_criteria:
        return {
            "candidate_criteria": candidate_criteria,
            "agentic_terms": [],
            "errors": errors,
        }
    if bool(candidate_criteria.get("no_rule_expected")):
        return {
            "candidate_criteria": candidate_criteria,
            "agentic_terms": [],
            "errors": errors,
        }

    rec = state.get("recommendation") or {}
    recommendation_text = str(rec.get("verbatim") or "")
    hitl_terms: list[dict[str, Any]] = list(candidate_criteria.get("hitl_terms") or [])

    def _walk(node: dict[str, Any] | None) -> None:
        if not node:
            return
        if node.get("kind") == "concept":
            criterion = dict(node.get("criterion") or {})
            candidates = list(criterion.get("candidates") or [])
            if _needs_agentic_retry(candidates) and not bool(
                criterion.get("resolver_turns")
            ):
                term = str(criterion.get("term") or "")
                expected_tag = _infer_expected_tag_for_term_obj(
                    {
                        "text": criterion.get("term"),
                        "source_text": criterion.get("source_text"),
                    },
                    is_action=False,
                )
                result = _run_agentic_resolver(term, expected_tag, recommendation_text)
                extra = list(result.get("best_candidates") or [])
                if extra:
                    merged = {
                        str(c.get("concept_id") or c.get("preferred_term") or ""): c
                        for c in (candidates + extra)
                    }
                    criterion["candidates"] = sorted(
                        merged.values(),
                        key=lambda c: float(c.get("score") or 0.0),
                        reverse=True,
                    )[:8]
                criterion["resolver_turns"] = int(result.get("resolver_turns") or 0)
                criterion["search_history"] = list(result.get("search_history") or [])
                if bool(result.get("needs_human_review")):
                    criterion["needs_human_review"] = True
                    hitl_terms.append(
                        {
                            "kind": "leaf",
                            "node_id": criterion.get("node_id"),
                            "term": term,
                            "reason": result.get("reason"),
                            "search_history": criterion.get("search_history") or [],
                            "best_candidates": list(
                                result.get("best_candidates") or []
                            ),
                        }
                    )
                node["criterion"] = criterion
            return
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk(child)

    _walk(candidate_criteria.get("logic_tree"))
    action = dict(candidate_criteria.get("action") or {})
    if (
        action
        and _needs_agentic_retry(list(action.get("candidates") or []))
        and not bool(action.get("resolver_turns"))
    ):
        term = str(action.get("term") or "")
        result = _run_agentic_resolver(term, "procedure", recommendation_text)
        extra = list(result.get("best_candidates") or [])
        if extra:
            merged = {
                str(c.get("concept_id") or c.get("preferred_term") or ""): c
                for c in (list(action.get("candidates") or []) + extra)
            }
            action["candidates"] = sorted(
                merged.values(),
                key=lambda c: float(c.get("score") or 0.0),
                reverse=True,
            )[:8]
        action["resolver_turns"] = int(result.get("resolver_turns") or 0)
        action["search_history"] = list(result.get("search_history") or [])
        if bool(result.get("needs_human_review")):
            action["needs_human_review"] = True
            hitl_terms.append(
                {
                    "kind": "action",
                    "term": term,
                    "reason": result.get("reason"),
                    "search_history": action.get("search_history") or [],
                    "best_candidates": list(result.get("best_candidates") or []),
                }
            )
        candidate_criteria["action"] = action

    for item in hitl_terms:
        errors.append(
            f"needs_human_review:{item.get('kind')}:{item.get('term') or item.get('node_id')}"
        )

    return {
        "candidate_criteria": candidate_criteria,
        "agentic_terms": hitl_terms,
        "errors": errors,
    }


def _build_partial_from_candidates(
    candidate_criteria: dict[str, Any], hitl_terms: list[dict[str, Any]]
) -> dict[str, Any]:
    def _walk(node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not node:
            return None
        out = dict(node)
        if out.get("kind") == "concept":
            criterion = dict(out.get("criterion") or {})
            cands = list(criterion.get("candidates") or [])
            best = cands[0] if cands else None
            out["criterion"] = {
                "node_id": criterion.get("node_id", ""),
                "term": criterion.get("term", ""),
                "source_text": criterion.get("source_text"),
                "snomed_concept_id": (best or {}).get("concept_id"),
                "preferred_term": (best or {}).get(
                    "preferred_term", criterion.get("term", "")
                ),
                "semantic_tag": (best or {}).get("semantic_tag", ""),
                "candidates": cands,
                "verification_status": (
                    "needs_human_review" if not best else "provisionally_verified"
                ),
                "verification_reason": "partial_hitl",
                "confidence": float((best or {}).get("score") or 0.0),
                "resolver_turns": criterion.get("resolver_turns"),
                "needs_human_review": not bool(best)
                or bool(criterion.get("needs_human_review")),
                "search_history": criterion.get("search_history"),
            }
            return out
        out["children"] = [
            c
            for c in (_walk(ch) for ch in (out.get("children") or []))
            if c is not None
        ]
        return out

    action = dict(candidate_criteria.get("action") or {})
    action_payload = None
    if action:
        cands = list(action.get("candidates") or [])
        best = cands[0] if cands else None
        action_payload = {
            "term": action.get("term", ""),
            "snomed_concept_id": (best or {}).get("concept_id"),
            "preferred_term": (best or {}).get(
                "preferred_term", action.get("term", "")
            ),
            "semantic_tag": (best or {}).get("semantic_tag", ""),
            "candidates": cands,
            "verification_status": (
                "needs_human_review" if not best else "provisionally_verified"
            ),
            "verification_reason": "partial_hitl",
            "confidence": float((best or {}).get("score") or 0.0),
            "resolver_turns": action.get("resolver_turns"),
            "needs_human_review": not bool(best)
            or bool(action.get("needs_human_review")),
            "search_history": action.get("search_history"),
        }
    return {
        "schema_version": 2,
        "logic_tree": _walk(candidate_criteria.get("logic_tree")),
        "action": action_payload,
        "needs_human_review": bool(hitl_terms),
        "hitl_terms": hitl_terms,
        "verifier": {"overall_status": "partial_hitl"},
    }


def _derive_hitl_terms_from_errors(
    candidate_criteria: dict[str, Any], errors: list[str]
) -> list[dict[str, Any]]:
    hitl_terms: list[dict[str, Any]] = list(candidate_criteria.get("hitl_terms") or [])
    if any(str(e).startswith("verifier_unresolved:action:") for e in errors):
        action = dict(candidate_criteria.get("action") or {})
        hitl_terms.append(
            {
                "kind": "action",
                "term": action.get("term"),
                "reason": "verifier_unresolved",
                "search_history": action.get("search_history") or [],
                "best_candidates": list(action.get("candidates") or []),
            }
        )

    def _walk(node: dict[str, Any] | None) -> None:
        if not node:
            return
        if node.get("kind") == "concept":
            criterion = dict(node.get("criterion") or {})
            if criterion.get("needs_human_review"):
                hitl_terms.append(
                    {
                        "kind": "leaf",
                        "node_id": criterion.get("node_id"),
                        "term": criterion.get("term"),
                        "reason": "needs_human_review",
                        "search_history": criterion.get("search_history") or [],
                        "best_candidates": list(criterion.get("candidates") or []),
                    }
                )
            return
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk(child)

    _walk(candidate_criteria.get("logic_tree"))
    return _dedupe_hitl_terms(hitl_terms)


def _dedupe_hitl_terms(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = (
            str(item.get("kind") or "")
            + ":"
            + str(item.get("node_id") or item.get("term") or "")
        )
        deduped[key] = item
    return list(deduped.values())


def _draft_rule_small(
    recommendation: dict[str, Any], coded_criteria: dict[str, Any]
) -> dict[str, Any]:
    from libs.llm_client.factory import create_llm

    payload = {
        "recommendation": {
            "id": recommendation.get("id"),
            "title": recommendation.get("title"),
            "section_title": recommendation.get("section_title"),
            "chapter_title": recommendation.get("chapter_title"),
            "verbatim": recommendation.get("verbatim"),
        },
        "coded_criteria": coded_criteria,
    }
    system = (
        "You are a clinical rule author. Output JSON only with keys "
        "`rule_summary`, `potential_risks`, and `clinical_rationale`."
    )
    resp = create_llm(tier="small").converse(
        system=system,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        json_mode=True,
        max_tokens=700,
        agent_task="guidance_rule_drafter",
    )
    parsed = _parse_json_object(resp.text or "", max_chars=4000)
    return (
        parsed
        if isinstance(parsed, dict)
        else {
            "rule_summary": "draft_unavailable",
            "potential_risks": [],
            "clinical_rationale": "",
        }
    )


def _review_rule_big(
    recommendation: dict[str, Any],
    coded_criteria: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    from libs.llm_client.factory import create_llm

    system = (
        "You are a senior clinical reviewer. Return JSON only with keys: "
        "`status` (approve|needs_fix|reject_to_hitl), `reason`, `revision_instructions`."
    )
    payload = {
        "recommendation": recommendation,
        "coded_criteria": coded_criteria,
        "draft": draft,
    }
    resp = create_llm(tier="big").converse(
        system=system,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        json_mode=True,
        max_tokens=700,
        agent_task="guidance_rule_reviewer",
    )
    parsed = _parse_json_object(resp.text or "", max_chars=4000)
    if isinstance(parsed, dict) and str(parsed.get("status") or "") in {
        "approve",
        "needs_fix",
        "reject_to_hitl",
    }:
        return parsed
    return {
        "status": "needs_fix",
        "reason": "unparseable_big_review",
        "revision_instructions": "Recheck semantic fidelity and referral/investigation intent.",
    }


def _apply_authoring_gate(
    recommendation: dict[str, Any], coded_criteria: dict[str, Any]
) -> dict[str, Any]:
    """Small draft -> big review -> optional small revision -> big final review."""
    draft = _draft_rule_small(recommendation, coded_criteria)
    first_review = _review_rule_big(recommendation, coded_criteria, draft)
    final_review = first_review
    if str(first_review.get("status") or "") == "needs_fix":
        revised = dict(draft)
        revised["revision_instructions"] = (
            first_review.get("revision_instructions") or ""
        )
        final_review = _review_rule_big(recommendation, coded_criteria, revised)
        draft = revised
    gate = {
        "draft": draft,
        "first_review": first_review,
        "final_review": final_review,
    }
    out = dict(coded_criteria)
    out["authoring_gate"] = gate
    status = str(final_review.get("status") or "")
    if status in {"needs_fix", "reject_to_hitl"}:
        out["needs_human_review"] = True
        terms = list(out.get("hitl_terms") or [])
        terms.append(
            {
                "kind": "rule",
                "term": str((recommendation or {}).get("id") or "rule"),
                "reason": str(final_review.get("reason") or status),
                "search_history": [],
                "best_candidates": [],
            }
        )
        out["hitl_terms"] = _dedupe_hitl_terms(terms)
    return out


def assemble_result(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    verified = verify_codes(state)
    if verified.get("coded_criteria") is not None:
        coded = dict(verified["coded_criteria"] or {})
        coded.setdefault("needs_human_review", bool(state.get("agentic_terms")))
        coded.setdefault("hitl_terms", list(state.get("agentic_terms") or []))
        try:
            coded = _apply_authoring_gate(state.get("recommendation") or {}, coded)
        except Exception:
            logger.exception(
                "Authoring gate failed; preserving coded criteria and routing to HITL."
            )
            coded["needs_human_review"] = True
        verified["coded_criteria"] = coded
        return verified

    candidate_criteria = state.get("candidate_criteria")
    hitl_terms = list(state.get("agentic_terms") or [])
    errors = list(verified.get("errors") or [])
    if candidate_criteria:
        derived_hitl = _derive_hitl_terms_from_errors(candidate_criteria, errors)
        hitl_terms = _dedupe_hitl_terms(hitl_terms + derived_hitl)
    if candidate_criteria and hitl_terms:
        partial = _build_partial_from_candidates(candidate_criteria, hitl_terms)
        try:
            partial = _apply_authoring_gate(state.get("recommendation") or {}, partial)
        except Exception:
            logger.exception("Authoring gate failed on partial output.")
        return {
            "coded_criteria": partial,
            "errors": errors,
            "llm_tokens": verified.get("llm_tokens")
            or dict(state.get("llm_tokens") or {}),
        }
    return verified


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
                "reason": str(
                    candidate_criteria.get("reason")
                    or "non_codable_service_recommendation"
                ),
                "verifier": {
                    "overall_status": "no_rule_expected",
                    "reason": str(
                        candidate_criteria.get("reason")
                        or "non_codable_service_recommendation"
                    ),
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
            from libs.llm_client.consensus import (
                run_consensus,
                _consensus_verifier_tier,
            )

            verdict = run_consensus(
                system_prompt=verifier_prompt,
                user_msg=_build_verifier_user_msg(rec, raw or {}, working, few_shot),
                parse_fn=_parse_verifier_output,
                fail_verdict=None,
                max_tokens=3000,
                json_mode=True,
                tier=_consensus_verifier_tier(),
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
                return {
                    "coded_criteria": None,
                    "errors": errors,
                    "llm_tokens": merged_tokens,
                }
            if (
                str(verifier_result.get("overall_status") or "") == "retry_search"
                and attempt == 0
            ):
                working = _rerun_requested_searches(working, verifier_result)
                continue
            if (
                str(verifier_result.get("overall_status") or "") == "rejected"
                and attempt == 0
                and _has_instruction_issue(verifier_result)
            ):
                logger.warning(
                    "Verifier rejected %s due to likely instruction/schema issue; retrying once.",
                    rec.get("id"),
                )
                continue
            break
        except TerminologyAPIError as exc:
            errors.append(f"terminology_api_unavailable:{exc}")
            return {
                "coded_criteria": None,
                "errors": errors,
                "llm_tokens": merged_tokens,
            }
        except Exception as exc:
            logger.exception("Verifier failed for recommendation %s", rec.get("id"))
            errors.append(f"verifier_error:{rec.get('id')}:{exc}")
            return {
                "coded_criteria": None,
                "errors": errors,
                "llm_tokens": merged_tokens,
            }

    if verifier_result is None:
        errors.append(f"verifier_empty:{rec.get('id')}")
        return {"coded_criteria": None, "errors": errors, "llm_tokens": merged_tokens}

    leaf_lookup, action_lookup = _candidate_lookup(working)
    decisions = {
        str(item.get("node_id") or ""): item
        for item in (verifier_result.get("leaf_decisions") or [])
        if item.get("node_id")
    }
    verified_tree, tree_errors = _apply_leaf_decisions(
        working.get("logic_tree"), decisions, leaf_lookup
    )
    errors.extend(tree_errors)

    action_payload = None
    action = working.get("action")
    if action:
        action_decision = verifier_result.get("action_decision") or {}
        action_id = str(action_decision.get("selected_concept_id") or "")
        candidate = action_lookup.get(action_id)
        selected_action, fallback_reason = _select_action_candidate(
            rec,
            str(action.get("term") or ""),
            list(action.get("candidates") or []),
            (
                candidate
                if str(action_decision.get("status") or "") == "verified"
                else None
            ),
        )
        if selected_action is None:
            errors.append(
                f"verifier_unresolved:action:{action_decision.get('reason') or 'no approved action'}"
            )
        else:
            action_payload = {
                "term": action.get("term", ""),
                "original_phrase": action.get("original_phrase"),
                "expansion_source": action.get("expansion_source"),
                "expanded_from": action.get("expanded_from"),
                "snomed_concept_id": selected_action.get("concept_id"),
                "preferred_term": selected_action.get(
                    "preferred_term", action.get("term", "")
                ),
                "semantic_tag": selected_action.get("semantic_tag", ""),
                "candidates": action.get("candidates") or [],
                "verification_status": "verified",
                "verification_reason": (
                    fallback_reason or str(action_decision.get("reason") or "")
                ),
                "confidence": float(
                    action_decision.get("confidence")
                    or selected_action.get("score")
                    or 0.0
                ),
                "resolver_turns": action.get("resolver_turns"),
                "needs_human_review": bool(action.get("needs_human_review")),
                "search_history": action.get("search_history"),
            }

    if (
        errors
        or verified_tree is None
        or (
            str(verifier_result.get("overall_status") or "") != "verified"
            and action_payload is None
        )
    ):
        logger.error(
            "Verifier rejected or left unresolved terms for %s — rule will NOT be written. Errors=%s",
            rec.get("id"),
            errors,
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
    return (
        "resolve"
        if (
            raw.get("logic_tree") is not None
            or raw.get("action")
            or raw.get("no_rule_expected")
        )
        else "end"
    )


def _should_verify(state: GuidanceRuleExtractionState) -> str:
    return "verify" if state.get("candidate_criteria") is not None else "end"


def batch_resolve(state: GuidanceRuleExtractionState) -> dict[str, Any]:
    return code_snomed(state)


def _should_batch(state: GuidanceRuleExtractionState) -> str:
    return "resolve" if state.get("expanded_criteria") is not None else "end"


def _should_agentic(state: GuidanceRuleExtractionState) -> str:
    return "agentic" if state.get("candidate_criteria") is not None else "end"


def build_guidance_rule_extraction_subgraph() -> CompiledStateGraph:
    """Build the exact guidance extraction subgraph."""
    g = StateGraph(GuidanceRuleExtractionState)
    g.add_node("resolve_prompt", resolve_prompt)
    g.add_node("extract_criteria", extract_criteria)
    g.add_node("expand_leaves", expand_leaves)
    g.add_node("batch_resolve", batch_resolve)
    g.add_node("agentic_resolve", agentic_resolve)
    g.add_node("assemble_result", assemble_result)
    g.add_edge(START, "resolve_prompt")
    g.add_edge("resolve_prompt", "extract_criteria")
    g.add_conditional_edges(
        "extract_criteria", _should_resolve, {"resolve": "expand_leaves", "end": END}
    )
    g.add_conditional_edges(
        "expand_leaves", _should_batch, {"resolve": "batch_resolve", "end": END}
    )
    g.add_conditional_edges(
        "batch_resolve", _should_agentic, {"agentic": "agentic_resolve", "end": END}
    )
    g.add_edge("agentic_resolve", "assemble_result")
    g.add_edge("assemble_result", END)
    return g.compile()
