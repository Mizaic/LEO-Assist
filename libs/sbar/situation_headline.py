"""Build a Situation headline from present coded facts.

Atlas:
  DO: DO-FE774247
  DI: DI-ED65569C
"""

from __future__ import annotations

import re
from typing import Any

_PMB_PHRASES = (
    "postmenopausal bleeding",
    "post-menopausal bleeding",
    "post menopausal bleeding",
    "postmenopausal vaginal bleeding",
    "post-menopausal vaginal bleeding",
    "post menopausal vaginal bleeding",
)

_ABSENT = frozenset({"absent", "negated", "refuted"})
_WEAK = (
    "postmenopausal state",
    "post menopausal for",
    "body mass",
    "blood pressure",
    "heart rate",
)


def headline_from_coded_facts(entities: list[dict[str, Any]] | None) -> str | None:
    """Return suspected site plus a present finding. Never name absent PMB."""
    suspected: list[str] = []
    findings: list[str] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() in _ABSENT:
            continue
        term = _short_term(entity)
        if not term or _is_weak(term):
            continue
        if _is_suspected(term, entity):
            suspected.append(term)
        elif _is_finding(term, entity):
            findings.append(term)
    parts = suspected[:1] + findings[:1]
    if not parts:
        return None
    return ". ".join(parts) + "."


def absent_finding_terms(entities: list[dict[str, Any]] | None) -> list[str]:
    """Terms coded absent, so Situation must not name them as the trigger."""
    out: list[str] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() not in _ABSENT:
            continue
        term = _short_term(entity)
        if term and term not in out:
            out.append(term)
    return out[:8]


def drop_invented_pmb(
    markdown: str,
    present_terms: list[str] | None = None,
    structured_headline: str | None = None,
) -> str:
    """Remove a PMB trigger the letter and codes do not support."""
    text = (markdown or "").strip()
    if not text or _pmb_is_present(present_terms):
        return markdown
    if not any(phrase in text.lower() for phrase in _PMB_PHRASES):
        return markdown
    kept = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip() and not any(phrase in part.lower() for phrase in _PMB_PHRASES)
    ]
    if kept:
        return " ".join(kept)
    return (structured_headline or "").strip() or markdown


def _pmb_is_present(present_terms: list[str] | None) -> bool:
    for term in present_terms or []:
        low = term.lower()
        if any(phrase in low for phrase in _PMB_PHRASES):
            return True
    return False


def present_finding_terms(entities: list[dict[str, Any]] | None) -> list[str]:
    """Present coded terms that may lead Situation."""
    out: list[str] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() in _ABSENT:
            continue
        term = _short_term(entity)
        if not term or _is_weak(term) or term in out:
            continue
        out.append(term)
    return out[:8]


def _short_term(entity: dict[str, Any]) -> str:
    raw = str(entity.get("term") or entity.get("text") or "").strip()
    if " (" in raw:
        raw = raw.split(" (", 1)[0].strip()
    return raw


def _is_weak(term: str) -> bool:
    low = term.lower()
    return any(token in low for token in _WEAK)


def _is_suspected(term: str, entity: dict[str, Any]) -> bool:
    low = term.lower()
    label = str(entity.get("label") or "").lower()
    return "suspected" in low or label == "situation"


def _is_finding(term: str, entity: dict[str, Any]) -> bool:
    label = str(entity.get("label") or "").lower()
    if label in {"finding", "disorder"}:
        return True
    return "discharge" in term.lower()
