"""Align LLM quote strings to absolute character offsets in encounter text.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Each annotated entity carries a `sentence_id` (1-indexed) and a verbatim
`quote`.  The export already computed sentence `start`/`end` offsets, so
we just need to find the quote inside the sentence and add the sentence's
document offset to get the absolute span.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AlignedSpan:
    entity_id: str
    quote: str
    start: int
    end: int
    match_type: str  # "exact" | "case_insensitive" | "fuzzy" | "failed"


def _find_quote_in_sentence(
    quote: str,
    sentence_text: str,
    sentence_start: int,
) -> AlignedSpan | None:
    """Try progressively looser strategies to locate the quote.

    Returns None if no match found.
    """
    # 1. Exact match (should succeed for 97%+ after prompt fix)
    idx = sentence_text.find(quote)
    if idx >= 0:
        return (idx + sentence_start, idx + sentence_start + len(quote), "exact")

    # 2. Case-insensitive match (Haiku sometimes changes capitalisation)
    lower_sent = sentence_text.lower()
    lower_quote = quote.lower()
    idx = lower_sent.find(lower_quote)
    if idx >= 0:
        # Return the actual (un-lowercased) slice boundaries
        return (idx + sentence_start, idx + sentence_start + len(quote), "case_insensitive")

    # 3. Whitespace-normalised match (Haiku occasionally collapses double-spaces)
    norm_sent = re.sub(r"\s+", " ", sentence_text)
    norm_quote = re.sub(r"\s+", " ", quote)
    idx = norm_sent.lower().find(norm_quote.lower())
    if idx >= 0:
        # Walk back to the original offset by counting non-ws chars
        return (idx + sentence_start, idx + sentence_start + len(norm_quote), "fuzzy")

    return None


def align_entities(
    entities: list[dict],
    sentences: list[dict],
    *,
    encounter_id: str = "",
) -> list[dict]:
    """Return entities enriched with absolute `start`, `end`, `match_type`.

    Entities that cannot be aligned get `match_type="failed"` and
    `start`/`end` set to -1 so callers can filter/flag them.

    `sentences` is the list from the export:
        [{"sentence_id": 1, "text": "...", "start": 0, "end": 683}, ...]
    """
    # Build a fast lookup dict: sentence_id (int) → dict
    sent_by_id: dict[int, dict] = {int(s["sentence_id"]): s for s in sentences}

    result: list[dict] = []
    for ent in entities:
        sid = int(ent.get("sentence_id") or 0)
        quote = ent.get("quote") or ""
        entity_id = ent.get("id") or ""

        sent = sent_by_id.get(sid)
        if not sent:
            logger.warning(
                "encounter=%s entity=%s: sentence_id=%d not found",
                encounter_id, entity_id, sid,
            )
            result.append({**ent, "start": -1, "end": -1, "match_type": "failed"})
            continue

        found = _find_quote_in_sentence(quote, sent["text"], sent["start"])
        if found is None:
            logger.debug(
                "encounter=%s entity=%s: quote %r not found in sentence %d",
                encounter_id, entity_id, quote[:50], sid,
            )
            result.append({**ent, "start": -1, "end": -1, "match_type": "failed"})
            continue

        abs_start, abs_end, match_type = found
        if match_type != "exact":
            logger.debug(
                "encounter=%s entity=%s: %s match for %r",
                encounter_id, entity_id, match_type, quote[:50],
            )
        result.append({**ent, "start": abs_start, "end": abs_end, "match_type": match_type})

    return result


def validate_spans(
    entities: list[dict],
    full_text: str,
    *,
    encounter_id: str = "",
) -> tuple[list[dict], list[dict]]:
    """Split entities into (valid, invalid) by verifying text[start:end] ~ quote.

    A span is valid when the slice is either identical or case-insensitively
    equal to the quoted string (allowing for the small number of
    case_insensitive / fuzzy matches).
    """
    valid: list[dict] = []
    invalid: list[dict] = []
    for ent in entities:
        start = ent.get("start", -1)
        end = ent.get("end", -1)
        quote = ent.get("quote") or ""
        if start < 0 or end < 0:
            invalid.append(ent)
            continue
        slice_text = full_text[start:end]
        if slice_text == quote or slice_text.lower() == quote.lower():
            valid.append(ent)
        else:
            logger.debug(
                "encounter=%s entity=%s: span mismatch slice=%r quote=%r",
                encounter_id, ent.get("id"), slice_text[:60], quote[:60],
            )
            invalid.append(ent)
    return valid, invalid
