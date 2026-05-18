"""Deterministic search term expansion (DI-LEO-AI-526).

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Single source of truth for the typo correction and synonym map used to
turn a reviewer's free-text query into the set of lower-case terms that
both the host search (`/care/encounters`) and the dry-run review queue
(`/admin/training` -- candidates + gold) use to filter rows server-side.

Mirrored verbatim by the TypeScript client module
`services/ui/src/components/mission-control/encounterRelevance.ts`. Keep
both in lock-step so the chips that decorate each row in the UI use the
same vocabulary that the server used to fetch them.

Pure-Python and dependency-free so any router can import it without
pulling in `libs/llm_client` (whose AWS / boto wiring is heavier than
needed for filter expansion).
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_MIN_TERM_LEN = 2
_MAX_TERMS = 12
_MAX_EXPANDED = _MAX_TERMS * 3

TYPO_MAP: dict[str, str] = {
    "breat": "breast",
    "wight": "weight",
    "lums": "lumps",
    "tumor": "tumour",
}

SYNONYM_MAP: dict[str, list[str]] = {
    "breast": ["breast", "mammary"],
    "lump": ["lump", "mass", "swelling", "nodule"],
    "weight": ["weight", "weightloss", "weight_loss", "cachexia"],
    "loss": ["loss", "losing", "reduced"],
    "cough": ["cough", "coughing"],
    "bleeding": ["bleeding", "blood_loss", "haemorrhage", "hemorrhage"],
}


def normalise_tokens(raw_query: str) -> list[str]:
    """Lower-case, typo-correct, and length-filter the query tokens.

    The result is the deterministic floor used by both `expand_search_terms`
    and the analytics-layer encounter query understanding.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(raw_query)]
    fixed = [TYPO_MAP.get(tok, tok) for tok in tokens]
    return [tok for tok in fixed if len(tok) >= _MIN_TERM_LEN]


def expand_search_terms(query: str | None) -> list[str]:
    """Expand a reviewer query into the deduplicated list of search terms.

    Returns an empty list for a blank or all-stopword query so callers
    can short-circuit and skip the term filter entirely.
    """
    if not query:
        return []
    tokens = normalise_tokens(query)[:_MAX_TERMS]
    if not tokens:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        for term in SYNONYM_MAP.get(tok, [tok]):
            if term in seen:
                continue
            seen.add(term)
            out.append(term)
            if len(out) >= _MAX_EXPANDED:
                return out
    return out


__all__ = [
    "TYPO_MAP",
    "SYNONYM_MAP",
    "normalise_tokens",
    "expand_search_terms",
]
