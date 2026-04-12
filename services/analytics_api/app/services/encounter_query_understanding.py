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


def understand_query(raw_query: str) -> QueryUnderstanding:
    original = raw_query.strip()
    tokens = _normalise_tokens(original)
    normalized = " ".join(tokens) if tokens else original
    rewritten, confidence, reasoning = _try_haiku_rewrite(normalized)
    expanded_terms = _expand_terms(_normalise_tokens(rewritten))
    fulltext_query = _build_fulltext_query(expanded_terms, rewritten)
    rewrite_applied = rewritten.strip().lower() != normalized.strip().lower()
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
