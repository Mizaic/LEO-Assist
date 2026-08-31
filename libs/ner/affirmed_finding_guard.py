"""Restore present when the local clause affirms the finding.

Form 'No [ ]' and distant dates must not invert 'X noted', 'uses X',
or 'new X'. True 'no X' / 'denies X' stay absent.

Atlas trace:
  DO: DO-15449C6E
  DI: DI-0F9542BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-15449C6E")
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FLIP = frozenset({"absent", "historical"})
_AFFIRM_RE = re.compile(
    r"\b(?:noted|observed|uses|using|new(?:\s+onset)?)\b",
    re.IGNORECASE,
)
_LOCAL_NEGATION_RE = re.compile(
    r"\b(?:no|denies|denied|without|not)\s+$",
    re.IGNORECASE,
)
_SPAN_NEGATION_RE = re.compile(
    r"\b(?:no|denies|denied|without|not)\s+(?!\[)",
    re.IGNORECASE,
)
_NEW_ONSET_RE = re.compile(r"\bnew(?:\s+onset)?\s+$", re.IGNORECASE)
_CLEAR_FINDING_RE = re.compile(r"\b(?:is|looks|appears)\s+clear\b", re.IGNORECASE)


def _sentence_for(ent: dict[str, Any]) -> str:
    return str(
        ent.get("evidence_sentence") or ent.get("sentence") or ent.get("text") or ""
    )


def _entity_text(ent: dict[str, Any]) -> str:
    return str(ent.get("text") or ent.get("evidence") or "")


def _entity_start(ent: dict[str, Any], text: str) -> int | None:
    start = ent.get("start")
    if isinstance(start, int) and 0 <= start < len(text):
        return start
    phrase = _entity_text(ent)
    if not phrase:
        return None
    found = text.lower().find(phrase.lower())
    return found if found >= 0 else None


def _has_local_negation(text: str, start: int) -> bool:
    return bool(_LOCAL_NEGATION_RE.search(text[:start]))


def _finding_window(text: str, start: int, ent: dict[str, Any]) -> str:
    phrase = _entity_text(ent)
    window_start = max(0, start - 12)
    window_end = min(len(text), start + max(len(phrase), 1))
    return text[window_start:window_end]


def _has_negation_near_finding(text: str, start: int, ent: dict[str, Any]) -> bool:
    if _has_local_negation(text, start):
        return True
    return bool(_SPAN_NEGATION_RE.search(_finding_window(text, start, ent)))


def _restore_present(ent: dict[str, Any], reason: str, preview: str) -> None:
    ent["assertion"] = "present"
    ent["_assertion_guard"] = reason
    logger.info("affirmed_finding_guard: restored present | text=%r", preview[:80])


def _context_marked_absent(ent: dict[str, Any]) -> bool:
    return (
        ent.get("_assertion_source") == "context" and ent.get("assertion") == "absent"
    )


def _should_restore(text: str, start: int, ent: dict[str, Any]) -> bool:
    if _context_marked_absent(ent):
        return False
    if _has_negation_near_finding(text, start, ent):
        return False
    prefix = text[:start]
    if _NEW_ONSET_RE.search(prefix):
        return True
    blob = f"{_entity_text(ent)} {text}"
    if _CLEAR_FINDING_RE.search(blob) and not re.search(
        r"\bnot\s+(?:is|looks|appears)?\s*clear\b", blob, re.IGNORECASE
    ):
        return True
    return bool(_AFFIRM_RE.search(text))


def fix_locally_affirmed_assertions(entities: list[dict[str, Any]]) -> None:
    """Restore present for locally affirmed findings marked absent/historical."""
    for ent in entities:
        if ent.get("assertion") not in _FLIP:
            continue
        text = _sentence_for(ent)
        if not text:
            continue
        start = _entity_start(ent, text)
        if start is None:
            continue
        if not _should_restore(text, start, ent):
            continue
        _restore_present(ent, "locally_affirmed", _entity_text(ent) or text)
