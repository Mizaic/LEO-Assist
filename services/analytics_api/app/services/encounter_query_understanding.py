"""Query understanding for encounter case-finding.

Provides:
- deterministic normalization and typo handling
- lexical fulltext query construction
- optional Haiku rewrite with fail-open fallback
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from libs.llm_client.factory import create_llm

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_MIN_TERM_LEN = 2
_MAX_TERMS = 12
_TYPO_MAP = {
    "breat": "breast",
    "wight": "weight",
    "lums": "lumps",
    "tumor": "tumour",
}
_SYNONYM_MAP = {
    "breast": ["breast", "mammary"],
    "lump": ["lump", "mass", "swelling", "nodule"],
    "weight": ["weight", "weightloss", "weight_loss", "cachexia"],
    "loss": ["loss", "losing", "reduced"],
    "cough": ["cough", "coughing"],
    "bleeding": ["bleeding", "blood_loss", "haemorrhage", "hemorrhage"],
}


@dataclass
class QueryUnderstanding:
    original_query: str
    normalized_query: str
    rewritten_query: str
    rewrite_applied: bool
    rewrite_source: str
    rewrite_confidence: float | None
    fulltext_query: str
    expanded_terms: list[str]
    reasoning: str | None
    clinical_synonyms: list[str]
    clinical_synonyms_source: str


def _normalise_tokens(raw_query: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(raw_query)]
    fixed = [_TYPO_MAP.get(tok, tok) for tok in tokens]
    return [tok for tok in fixed if len(tok) >= _MIN_TERM_LEN]


def _expand_terms(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for tok in tokens[:_MAX_TERMS]:
        out.extend(_SYNONYM_MAP.get(tok, [tok]))
    # stable unique
    seen: set[str] = set()
    deduped: list[str] = []
    for term in out:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped[: _MAX_TERMS * 3]


def _build_fulltext_query(expanded_terms: list[str], rewritten_query: str) -> str:
    quoted_phrase = rewritten_query.strip()
    parts = [f'"{quoted_phrase}"'] if quoted_phrase else []
    for term in expanded_terms:
        safe = re.sub(r"[^A-Za-z0-9_]", "", term)
        if not safe:
            continue
        parts.append(f"{safe}*")
    return " OR ".join(parts) if parts else quoted_phrase


def _llm_rewrite_enabled() -> bool:
    return str(os.getenv("ENCOUNTER_QUERY_REWRITE_ENABLED", "false")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _try_haiku_rewrite(normalized_query: str) -> tuple[str, float | None, str | None]:
    if not _llm_rewrite_enabled():
        return normalized_query, None, None
    try:
        client = create_llm(provider="aws", tier="small")
        system = (
            "You rewrite clinical search queries for encounter retrieval. "
            "Return strict JSON with keys: rewritten_query, confidence, reasoning. "
            "Keep intent unchanged. Correct spelling. Expand only clinically-relevant terms."
        )
        user = json.dumps({"query": normalized_query})
        response = client.converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=200,
            temperature=0.0,
            json_mode=True,
            agent_task="encounter_query_rewriter",
        )
        payload = json.loads(response.text)
        rewritten = str(payload.get("rewritten_query") or normalized_query).strip()
        confidence = payload.get("confidence")
        if isinstance(confidence, int):
            confidence = float(confidence)
        if not isinstance(confidence, float):
            confidence = None
        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, str):
            reasoning = None
        return rewritten or normalized_query, confidence, reasoning
    except Exception:
        logger.warning(
            "Haiku query rewrite unavailable -- fail-open to normalized query"
        )
        return normalized_query, None, None


_CLINICAL_SYNONYM_CACHE: dict[str, tuple[list[str], str]] = {}
_CLINICAL_SYNONYM_CACHE_MAX = 256
_CLINICAL_SYNONYM_LIMIT = 12

_CLINICAL_SYNONYM_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "submit_clinical_synonyms",
                "description": (
                    "Submit clinical synonyms / equivalent phrases for a "
                    "clinician encounter search query. Used to highlight "
                    "matching wording in retrieved encounter notes."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "synonyms": {
                                "type": "array",
                                "minItems": 0,
                                "maxItems": _CLINICAL_SYNONYM_LIMIT,
                                "items": {"type": "string"},
                                "description": (
                                    "Up to 12 short phrases or single "
                                    "terms a clinician might write in "
                                    "free-text notes for the SAME "
                                    "finding. Include UK and US "
                                    "spellings, common abbreviations, "
                                    "lay wording, and tightly related "
                                    "findings. Do NOT include broader "
                                    "categories or unrelated concepts."
                                ),
                            }
                        },
                        "required": ["synonyms"],
                    }
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": "submit_clinical_synonyms"}},
}


def _clinical_synonyms_enabled() -> bool:
    """Default ON. Disable explicitly with ENCOUNTER_QUERY_SYNONYMS_ENABLED=false."""
    return str(
        os.getenv("ENCOUNTER_QUERY_SYNONYMS_ENABLED", "true")
    ).lower() in {"1", "true", "yes", "on"}


def _clean_synonym_list(raw_synonyms: list[Any]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for entry in raw_synonyms:
        if not isinstance(entry, str):
            continue
        term = entry.strip()
        if not term or len(term) < 3:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(term)
        if len(cleaned) >= _CLINICAL_SYNONYM_LIMIT:
            break
    return cleaned


def _extract_synonyms_from_response(response: Any) -> list[str]:
    """Pull a synonyms list from a Bedrock LLMResponse.

    Prefers the structured tool_use input (guaranteed-shape JSON
    against the toolSpec schema). Falls back to parsing JSON out of
    free text in case the model bypassed the tool.
    """
    tool_uses = list(getattr(response, "tool_uses", []) or [])
    for tu in tool_uses:
        if not isinstance(tu, dict):
            continue
        if tu.get("name") != "submit_clinical_synonyms":
            continue
        payload = tu.get("input") or {}
        raw = payload.get("synonyms")
        if isinstance(raw, list):
            return _clean_synonym_list(raw)
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return []
    cleaned_text = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
    try:
        payload = json.loads(cleaned_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    raw = payload.get("synonyms") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    return _clean_synonym_list(raw)


def _expand_clinical_synonyms(normalized_query: str) -> tuple[list[str], str]:
    """Return clinical synonyms / equivalent phrases for highlighting.

    The output is intentionally separate from `expanded_terms` so it
    does not affect ranking. It is used by the curator UI to highlight
    rows that matched semantically (e.g. "swollen abdomen" should also
    highlight "abdominal distension", "distended abdomen", "ascites").

    Uses a Bedrock toolConfig to force structured JSON output (the
    model can only return via the submit_clinical_synonyms tool).
    Cached in-process by normalised query; fail-open to an empty list.
    """
    query = normalized_query.strip()
    if not query:
        return [], "empty"
    cached = _CLINICAL_SYNONYM_CACHE.get(query)
    if cached is not None:
        return list(cached[0]), cached[1]
    if not _clinical_synonyms_enabled():
        return [], "disabled"
    try:
        client = create_llm(provider="aws", tier="small")
        system = (
            "You generate clinical synonyms for a UK general-practice "
            "encounter search. You MUST call the "
            "submit_clinical_synonyms tool exactly once with up to 12 "
            "short clinical synonyms for the user's query. Include UK "
            "and US spellings, common abbreviations, lay wording, and "
            "tightly related findings. Do NOT include broader "
            "categories or unrelated concepts."
        )
        user = (
            f"Query: {query}\n\n"
            "Return synonyms via the submit_clinical_synonyms tool."
        )
        response = client.converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=400,
            temperature=0.0,
            tool_config=_CLINICAL_SYNONYM_TOOL_CONFIG,
            json_mode=True,
            agent_task="clinical_synonym_expansion",
        )
        cleaned = _extract_synonyms_from_response(response)
        source = "haiku" if cleaned else "no_synonyms"
        if len(_CLINICAL_SYNONYM_CACHE) >= _CLINICAL_SYNONYM_CACHE_MAX:
            _CLINICAL_SYNONYM_CACHE.pop(next(iter(_CLINICAL_SYNONYM_CACHE)))
        _CLINICAL_SYNONYM_CACHE[query] = (cleaned, source)
        return list(cleaned), source
    except Exception:
        logger.warning(
            "Clinical synonym expansion unavailable -- highlighting will use "
            "deterministic terms only",
            exc_info=True,
        )
        return [], "error"


def understand_query(raw_query: str) -> QueryUnderstanding:
    original = raw_query.strip()
    tokens = _normalise_tokens(original)
    normalized = " ".join(tokens) if tokens else original
    rewritten, confidence, reasoning = _try_haiku_rewrite(normalized)
    expanded_terms = _expand_terms(_normalise_tokens(rewritten))
    fulltext_query = _build_fulltext_query(expanded_terms, rewritten)
    rewrite_applied = rewritten.strip().lower() != normalized.strip().lower()
    clinical_synonyms, synonyms_source = _expand_clinical_synonyms(normalized)
    return QueryUnderstanding(
        original_query=original,
        normalized_query=normalized,
        rewritten_query=rewritten,
        rewrite_applied=rewrite_applied,
        rewrite_source="haiku" if confidence is not None else "deterministic",
        rewrite_confidence=confidence,
        fulltext_query=fulltext_query,
        expanded_terms=expanded_terms,
        reasoning=reasoning,
        clinical_synonyms=clinical_synonyms,
        clinical_synonyms_source=synonyms_source,
    )


def feature_match_rationale(
    *, text: str | None, expanded_terms: list[str]
) -> dict[str, Any]:
    source = (text or "").lower()
    hits = [t for t in expanded_terms if t and t.lower() in source]
    return {
        "term_hits": len(hits),
        "hit_terms": hits[:8],
        "term_coverage": (len(hits) / max(1, len(expanded_terms))),
    }
