"""Locate an extracted fact by its own words before ConText judges it.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B7A69F26")

Character offsets on an extracted fact are not trustworthy by the time
they reach the assertion layer. ``SpanResolver`` hands back a fallback
span when it cannot find a surface form, and character 0 is the top of the
letter. A fact judged against the document header always comes back
``present``, because a header carries no negation cue -- so the negation
layer goes quiet exactly when it is needed.

This module removes that failure mode. Each fact is located by its own
text: offsets that already hold that text are kept, offsets that do not
are re-found. A fact whose text is nowhere in the document is reported as
unresolved so the caller can flag it, rather than letting it pass as a
confirmed finding.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

UNRESOLVED_KEY = "context_span_unresolved"
_PHI_TOKEN = re.compile(
    r"\[(?:date|person|nhs_number|postcode|phone|email|address|"
    r"organisation|location|staff_id)\]",
    re.IGNORECASE,
)
_PHI_GAP = r".{1,40}?"
_FILLER_WORD = r"(?:are|is|was|were|be|been|the|a|an)"
_WORD_GAP = rf"\s+(?:{_FILLER_WORD}\s+)?"


def span_holds_entity_text(
    text: str, encounter_text: str, start: int, end: int
) -> bool:
    """True when the offsets already point at the entity's own text."""
    if start < 0 or end <= start or end > len(encounter_text):
        return False
    return encounter_text[start:end].strip().lower() == text.strip().lower()


def _flexible_literal(text: str) -> str:
    """Escape words; allow wrap whitespace and one dropped filler word."""
    words = text.split()
    if not words:
        return re.escape(text)
    return _WORD_GAP.join(re.escape(w) for w in words)


def _whitespace_flexible_pattern(needle: str) -> re.Pattern[str] | None:
    words = needle.strip().split()
    if len(words) < 2:
        return None
    return re.compile(_flexible_literal(needle))


def _placeholder_pattern(needle: str) -> re.Pattern[str] | None:
    """Build a raw-letter search when the extractor used a PHI token."""
    if not _PHI_TOKEN.search(needle):
        return None
    parts = _PHI_TOKEN.split(needle)
    tokens = _PHI_TOKEN.findall(needle)
    out: list[str] = []
    for index, part in enumerate(parts):
        out.append(_flexible_literal(part))
        if index < len(tokens):
            out.append(_PHI_GAP)
    return re.compile("".join(out))


def span_appears_in_text(haystack: str, needle: str) -> bool:
    """True when needle, or its PHI-token pattern, appears in haystack."""
    if not needle.strip() or not haystack:
        return False
    if needle.strip().lower() in haystack.lower():
        return True
    return find_entity_text(haystack.lower(), needle, {}) is not None


def find_entity_text(
    encounter_text_lower: str,
    text: str,
    cursors: dict[str, int],
) -> tuple[int, int] | None:
    """Locate ``text`` in the document, keeping repeated mentions distinct.

    ``cursors`` carries the end of the previous match for each surface
    form, so a second mention of the same words does not collapse onto the
    first. A cursor that runs off the end falls back to a search from the
    start rather than reporting the fact as missing.
    """
    needle = text.strip().lower()
    if not needle:
        return None
    idx = encounter_text_lower.find(needle, cursors.get(needle, 0))
    if idx < 0:
        idx = encounter_text_lower.find(needle)
    if idx >= 0:
        cursors[needle] = idx + len(needle)
        return idx, idx + len(needle)
    found = _find_placeholder_span(encounter_text_lower, needle, cursors)
    if found is not None:
        return found
    return _find_whitespace_flexible_span(encounter_text_lower, needle, cursors)


def _search_pattern(
    haystack: str,
    needle: str,
    cursors: dict[str, int],
    pattern: re.Pattern[str] | None,
) -> tuple[int, int] | None:
    if pattern is None:
        return None
    match = pattern.search(haystack, cursors.get(needle, 0)) or pattern.search(haystack)
    if match is None:
        return None
    cursors[needle] = match.end()
    return match.start(), match.end()


def _find_placeholder_span(
    haystack: str, needle: str, cursors: dict[str, int]
) -> tuple[int, int] | None:
    return _search_pattern(haystack, needle, cursors, _placeholder_pattern(needle))


def _find_whitespace_flexible_span(
    haystack: str, needle: str, cursors: dict[str, int]
) -> tuple[int, int] | None:
    return _search_pattern(
        haystack, needle, cursors, _whitespace_flexible_pattern(needle)
    )


def resolve_context_spans(
    encounter_text: str,
    entities: list[dict],
    indices: list[int],
) -> list[tuple[int, int, int]]:
    """Return ``(entity_index, start, end)`` for entities ConText can judge.

    Entities that cannot be located are given ``context_span_unresolved``
    and left out of the returned list. Leaving one in would have ConText
    read words belonging to a different part of the letter, which is how a
    denied finding reaches the record as present.
    """
    lowered = encounter_text.lower()
    cursors: dict[str, int] = {}
    resolved: list[tuple[int, int, int]] = []
    unresolved = 0
    for idx in indices:
        entity = entities[idx]
        text = str(entity.get("text") or "")
        start = int(entity.get("start") or 0)
        end = int(entity.get("end") or start)
        if span_holds_entity_text(text, encounter_text, start, end):
            resolved.append((idx, start, end))
            continue
        found = find_entity_text(lowered, text, cursors)
        if found is None:
            entity[UNRESOLVED_KEY] = True
            entity["assertion"] = "assertion_unverified"
            unresolved += 1
            continue
        resolved.append((idx, found[0], found[1]))
    if unresolved:
        logger.warning(
            "context_span_unresolved=%d of %d entities -- assertion not "
            "checked for these facts; they need a human to read them",
            unresolved,
            len(indices),
        )
    return resolved
