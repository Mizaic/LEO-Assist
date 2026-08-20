"""Stop negation leaking past a positive contrast such as 'but does have'.

Atlas:
  DI: DI-0F9542BF
  DO: DO-15449C6E
  VT: VT-A1919820
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-15449C6E")
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_CONTRAST_POSITIVE_RE = re.compile(
    r"\b(?:but|however|although|except(?:\s+that)?|whereas)\s+"
    r"(?:"
    r"does\s+have|does\s+report|"
    r"(?:he|she|they|patient)\s+(?:does\s+)?(?:have|has|report|reports)|"
    r"has|have|reports?|presents?\s+with|complains?\s+of|"
    r"there\s+(?:is|are)"
    r")\b",
    re.IGNORECASE,
)

_NEGATION_CUE_RE = re.compile(
    r"\b(?:denies|denied|deny|no|without|negative\s+for)\b",
    re.IGNORECASE,
)

_LOCAL_NEGATION_RE = re.compile(
    r"\b(?:no|denies|denied|without|not)\s+$",
    re.IGNORECASE,
)


def _entity_text(ent: dict[str, Any]) -> str:
    return str(ent.get("text") or ent.get("evidence") or "")


def _sentence_for(ent: dict[str, Any]) -> str:
    return str(
        ent.get("evidence_sentence") or ent.get("sentence") or ent.get("text") or ""
    )


def _contrast_span(text: str) -> tuple[int, int] | None:
    match = _CONTRAST_POSITIVE_RE.search(text)
    if match is None:
        return None
    if not _NEGATION_CUE_RE.search(text[: match.start()]):
        return None
    return match.start(), match.end()


def _entity_start(ent: dict[str, Any], text: str, after: int) -> int | None:
    start = ent.get("start")
    if isinstance(start, int) and 0 <= start < len(text):
        return start
    phrase = _entity_text(ent)
    if not phrase:
        return None
    found = text.lower().find(phrase.lower(), after)
    return found if found >= 0 else None


def _has_local_negation(text: str, start: int) -> bool:
    return bool(_LOCAL_NEGATION_RE.search(text[:start]))


def contrast_terminates_modifier(
    text: str, modifier_end: int, entity_start: int
) -> bool:
    """True when a positive contrast sits between a cue and the entity."""
    if entity_start <= modifier_end or modifier_end < 0:
        return False
    return bool(_CONTRAST_POSITIVE_RE.search(text[modifier_end:entity_start]))


def _restore_present(ent: dict[str, Any], preview: str) -> None:
    ent["assertion"] = "present"
    ent["_assertion_guard"] = "contrast_positive"
    logger.info("contrast_positive_guard: restored present | text=%r", preview[:80])


def fix_contrast_positive_false_absent(entities: list[dict[str, Any]]) -> None:
    """Restore present for findings after 'denies X, but does have Y'.

    Leaves the denied finding absent. Leaves a later 'no Y' absent.
    Idempotent.
    """
    for ent in entities:
        if ent.get("assertion") != "absent":
            continue
        text = _sentence_for(ent)
        span = _contrast_span(text)
        if span is None:
            continue
        _, cue_end = span
        start = _entity_start(ent, text, cue_end)
        if start is None or start < cue_end:
            continue
        if _has_local_negation(text, start):
            continue
        _restore_present(ent, _entity_text(ent) or text)
