"""Helpers for observable-entity span cleanup and measurement parsing.

This module centralizes deterministic rules used in:
- label verification normalization (gold-label correction)
- runtime model extraction post-processing
"""
from __future__ import annotations

import re
from typing import Any

_READ_CODE_RE = re.compile(r"\([A-Za-z0-9]{3,8}\.{0,2}\)")
_REF_RANGE_RE = re.compile(r"\[(?P<range>[^\]]+)\]")
_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*(?:\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?))\s*(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)
_KNOWN_UNIT_TOKEN_RE = re.compile(
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|ml|l|mol|fl|%|mmhg|kpa|bpm|10\^)",
    re.IGNORECASE,
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find_nearest_start(
    encounter_text: str,
    span_text: str,
    around: int = 0,
    existing_entities: list[dict[str, Any]] | None = None,
) -> int | None:
    if not span_text:
        return None

    def _overlaps_existing(candidate: int) -> bool:
        if not existing_entities:
            return False
        cand_end = candidate + len(span_text)
        for e in existing_entities:
            es = int(e.get("start", 0) or 0)
            ee = int(e.get("end", 0) or 0)
            if candidate < ee and cand_end > es:
                return True
        return False

    def _best(positions: list[int]) -> int | None:
        ranked = sorted(positions, key=lambda p: abs(p - around))
        for p in ranked:
            if not _overlaps_existing(p):
                return p
        return ranked[0] if ranked else None

    positions: list[int] = []
    pos = encounter_text.find(span_text)
    while pos != -1:
        positions.append(pos)
        pos = encounter_text.find(span_text, pos + 1)
    if positions:
        return _best(positions)

    hay = encounter_text.lower()
    needle = span_text.lower()
    positions = []
    pos = hay.find(needle)
    while pos != -1:
        positions.append(pos)
        pos = hay.find(needle, pos + 1)
    if positions:
        return _best(positions)
    return None


def parse_measurement_from_text(text: str) -> dict[str, str]:
    """Parse numeric measurement components from free text.

    Returns keys:
      - numeric_value (optional)
      - unit (optional)
      - reference_range (optional)
      - value_span (optional full value+unit snippet)
    """
    out: dict[str, str] = {}
    raw = text or ""
    ref_match = _REF_RANGE_RE.search(raw)
    if ref_match:
        out["reference_range"] = _collapse_ws(ref_match.group("range"))

    # Strip code fragments and ranges before measurement matching so values like
    # "(42J..)" are never interpreted as numeric results.
    searchable = _READ_CODE_RE.sub(" ", raw)
    searchable = _REF_RANGE_RE.sub(" ", searchable)

    matches = list(_VALUE_UNIT_RE.finditer(searchable))
    if not matches:
        return out

    # Prefer clinically plausible unit patterns; then prefer the right-most
    # candidate because values usually occur after the test name.
    plausible = [m for m in matches if _KNOWN_UNIT_TOKEN_RE.search(m.group("unit") or "")]
    if not plausible:
        return out
    match = plausible[-1]

    value = _collapse_ws(match.group("value"))
    unit = _collapse_ws(match.group("unit"))
    if value:
        out["numeric_value"] = value
    if unit:
        out["unit"] = unit
    out["value_span"] = _collapse_ws(searchable[match.start():match.end()])
    return out


def normalize_observable_entities(
    encounter_text: str,
    entities: list[dict[str, Any]],
    *,
    add_qualifier_value: bool = True,
    preserve_existing_structured: bool = True,
) -> list[dict[str, Any]]:
    """Clean observable spans and attach value/unit/reference-range.

    - strips embedded Read/CTV3 code fragments, e.g. "(XE2q0)"
    - strips bracketed reference ranges from observable span text
    - splits observable test name from value/unit portion
    - writes structured fields: value, unit, reference_range
    - optionally adds a qualifier_value entity for value+unit text
    - preserves existing structured fields by default (no silent overwrite)
    """
    updated = [dict(e) for e in entities]
    extras: list[dict[str, Any]] = []

    for ent in updated:
        if str(ent.get("label", "")) != "observable_entity":
            continue

        original_text = str(ent.get("text", ""))
        around = int(ent.get("start", 0) or 0)

        parsed = parse_measurement_from_text(original_text)
        existing_value = str(ent.get("value", "") or "").strip()
        existing_unit = str(ent.get("unit", "") or "").strip()
        existing_range = str(ent.get("reference_range", "") or "").strip()

        if parsed.get("numeric_value") and (not preserve_existing_structured or not existing_value):
            ent["value"] = parsed["numeric_value"]
        if parsed.get("unit") and (not preserve_existing_structured or not existing_unit):
            ent["unit"] = parsed["unit"]
        if parsed.get("reference_range") and (not preserve_existing_structured or not existing_range):
            ent["reference_range"] = parsed["reference_range"]

        # Remove code snippets and bracketed ranges from display span.
        stripped = _READ_CODE_RE.sub(" ", original_text)
        stripped = _REF_RANGE_RE.sub(" ", stripped)
        stripped = _collapse_ws(stripped)

        value_span = parsed.get("value_span", "")
        if value_span:
            value_pos = stripped.lower().find(value_span.lower())
            if value_pos > 0:
                stripped = _collapse_ws(stripped[:value_pos].strip(" -:;,"))
            elif value_pos == 0:
                after = stripped[len(value_span):]
                after_clean = _collapse_ws(after.strip(" -:;,"))
                if after_clean:
                    stripped = after_clean

        if stripped:
            ent["text"] = stripped
            new_start = _find_nearest_start(encounter_text, stripped, around=around)
            if new_start is not None:
                ent["start"] = new_start
                ent["end"] = new_start + len(stripped)

        if add_qualifier_value and value_span:
            value_start = _find_nearest_start(
                encounter_text,
                value_span,
                around=int(ent.get("end", around) or around),
            )
            if value_start is not None:
                duplicate = any(
                    str(e.get("label", "")) == "qualifier_value"
                    and _collapse_ws(str(e.get("text", ""))).lower().strip() == value_span.lower().strip()
                    for e in updated + extras
                )
                if not duplicate:
                    extras.append(
                        {
                            "text": value_span,
                            "label": "qualifier_value",
                            "start": value_start,
                            "end": value_start + len(value_span),
                            "confidence": float(ent.get("confidence", 0.0) or 0.0),
                        }
                    )

    if extras:
        updated.extend(extras)
    return updated
