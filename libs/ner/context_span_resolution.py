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

logger = logging.getLogger(__name__)

UNRESOLVED_KEY = "context_span_unresolved"


def span_holds_entity_text(
    text: str, encounter_text: str, start: int, end: int
) -> bool:
    """True when the offsets already point at the entity's own text."""
    if start < 0 or end <= start or end > len(encounter_text):
        return False
    return encounter_text[start:end].strip().lower() == text.strip().lower()


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
    if idx < 0:
        return None
    cursors[needle] = idx + len(needle)
    return idx, idx + len(needle)


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
