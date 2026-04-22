"""Helpers for observable-entity span cleanup and measurement parsing.

Atlas trace:
  DO: DO-8EF2EC20
  DI: DI-2F963FC6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8EF2EC20")

This module centralizes deterministic rules used in:
- label verification normalization (gold-label correction)
- runtime model extraction post-processing

Compound lab-result handling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Lab result lines often contain three distinct concepts in a single span::

    Mean cell haemoglobin level (XE2pb) 22.5 pg [27 - 32] - Outside reference range
    ├── observable_entity  "Mean cell haemoglobin level"   (what was measured)
    ├── qualifier_value    "22.5 pg"                       (the result)
    └── finding            "Outside reference range"        (the interpretation)

``normalize_observable_entities`` now detects interpretation suffixes and emits
a separate ``finding`` entity for them.  The finding entity's SNOMED code is
resolved downstream by the coding resolver, which can use the
``/concepts/{id}/related`` API endpoint to navigate from the resolved
observable_entity concept to its associated finding via the ``INTERPRETS``
relationship.
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

# "now <value> <unit>" (or "currently"/"today") flags the value reported AFTER
# the marker as the current measurement. Used to handle expressions such as
# "weight loss 10kg - now 79kg" where 10kg is a delta (weight change), not the
# observable's current value -- only the 79kg should become the linked value.
_CURRENT_VALUE_MARKER_RE = re.compile(
    r"\b(?:now|currently|today)\b\s*[:\-]?\s*"
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?)\s*"
    r"(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)
_TRAILING_CURRENT_MARKER_RE = re.compile(
    r"[\s\-:;,]*\b(?:now|currently|today)\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Interpretation-suffix detection
# ---------------------------------------------------------------------------
# Ordered from most specific to least specific so that "very high" is captured
# before "high".  Each entry maps to a normalised qualifier key.
_INTERPRETATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"outside\s+reference\s+range", re.I), "outside_reference_range"),
    (re.compile(r"above\s+reference\s+range", re.I), "above_reference_range"),
    (re.compile(r"below\s+reference\s+range", re.I), "below_reference_range"),
    (re.compile(r"within\s+reference\s+range", re.I), "within_reference_range"),
    (re.compile(r"out(?:\s+of)?\s+range", re.I), "outside_reference_range"),
    (re.compile(r"in\s+range", re.I), "within_reference_range"),
    (re.compile(r"above\s+range", re.I), "above_reference_range"),
    (re.compile(r"below\s+range", re.I), "below_reference_range"),
    (re.compile(r"very\s+high", re.I), "very_high"),
    (re.compile(r"very\s+low", re.I), "very_low"),
    (re.compile(r"high\b", re.I), "high"),
    (re.compile(r"low\b", re.I), "low"),
    (re.compile(r"elevated\b", re.I), "high"),
    (re.compile(r"raised\b", re.I), "high"),
    (re.compile(r"reduced\b", re.I), "low"),
    (re.compile(r"abnormal\b", re.I), "abnormal"),
    (re.compile(r"normal\b", re.I), "normal"),
    (re.compile(r"borderline\b", re.I), "borderline"),
]

# Separator characters that may appear between value and interpretation.
_INTERP_SEP_RE = re.compile(r"^[\s\-–:,;]+")


def _detect_interpretation(text: str) -> tuple[str, str] | None:
    """Return ``(matched_text, qualifier_key)`` if *text* starts with an
    interpretation phrase (after leading separators), else ``None``.

    Only matches at the start of *text* (after optional separator tokens).
    """
    sep_m = _INTERP_SEP_RE.match(text)
    after_sep = text[sep_m.end() :] if sep_m else text
    for pat, key in _INTERPRETATION_PATTERNS:
        m = pat.match(after_sep)
        if m:
            matched = m.group(0)
            # The "raw" text in the original includes the leading separator.
            full_raw = (sep_m.group(0) if sep_m else "") + matched
            return full_raw.strip(), key
    return None


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

    # Strong override: "now <value> <unit>" reports the current measurement.
    # Any earlier number in the same span is a delta (e.g. "weight loss 10kg")
    # and must not become the observable's value.
    now_match = _CURRENT_VALUE_MARKER_RE.search(searchable)
    if now_match and _KNOWN_UNIT_TOKEN_RE.search(now_match.group("unit") or ""):
        value = _collapse_ws(now_match.group("value"))
        unit = _collapse_ws(now_match.group("unit"))
        if value and unit:
            out["numeric_value"] = value
            out["unit"] = unit
            value_start = now_match.start("value")
            value_end = now_match.end("unit")
            out["value_span"] = _collapse_ws(searchable[value_start:value_end])
            out["current_value_marker"] = "now"
            return out

    matches = list(_VALUE_UNIT_RE.finditer(searchable))
    if not matches:
        return out

    # Prefer clinically plausible unit patterns; then prefer the right-most
    # candidate because values usually occur after the test name.
    plausible = [
        m for m in matches if _KNOWN_UNIT_TOKEN_RE.search(m.group("unit") or "")
    ]
    if not plausible:
        return out
    match = plausible[-1]

    value = _collapse_ws(match.group("value"))
    unit = _collapse_ws(match.group("unit"))
    if value:
        out["numeric_value"] = value
    if unit:
        out["unit"] = unit
    out["value_span"] = _collapse_ws(searchable[match.start() : match.end()])
    return out


def normalize_observable_entities(
    encounter_text: str,
    entities: list[dict[str, Any]],
    *,
    add_qualifier_value: bool = True,
    preserve_existing_structured: bool = True,
    emit_interpretation_finding: bool = True,
) -> list[dict[str, Any]]:
    """Clean observable spans and attach value/unit/reference-range.

    - strips embedded Read/CTV3 code fragments, e.g. "(XE2q0)"
    - strips bracketed reference ranges from observable span text
    - splits observable test name from value/unit portion
    - writes structured fields: value, unit, reference_range
    - optionally adds a qualifier_value entity for value+unit text
    - optionally emits a **finding** entity for interpretation suffixes such
      as "Outside reference range", "High", "Low" (see ``emit_interpretation_finding``)
    - preserves existing structured fields by default (no silent overwrite)

    Interpretation finding emission
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    When ``emit_interpretation_finding=True`` (the default), if the lab line
    carries an interpretation phrase after the numeric result, a separate entity
    ``{"label": "finding", "text": ..., "interpretation_qualifier": ...,
    "parent_observable_text": ...}`` is appended.  The coding resolver uses the
    ``/concepts/{id}/related`` endpoint to map the observable_entity concept to
    its SNOMED finding via the ``INTERPRETS`` relationship.
    """
    updated = [dict(e) for e in entities]
    extras: list[dict[str, Any]] = []

    for ent in updated:
        raw_label = str(ent.get("label", "")).lower().replace(" ", "_")
        if raw_label != "observable_entity":
            continue

        original_text = str(ent.get("text", ""))
        around = int(ent.get("start", 0) or 0)

        parsed = parse_measurement_from_text(original_text)
        existing_value = str(ent.get("value", "") or "").strip()
        existing_unit = str(ent.get("unit", "") or "").strip()
        existing_range = str(ent.get("reference_range", "") or "").strip()
        # "now <value>" is a strong clinical signal that the post-marker value
        # is the current measurement, so it overrides any pre-set value the
        # extractor (or upstream LLM) supplied for the earlier delta.
        force_override = parsed.get("current_value_marker") == "now"

        if parsed.get("numeric_value") and (
            not preserve_existing_structured or not existing_value or force_override
        ):
            ent["value"] = parsed["numeric_value"]
        if parsed.get("unit") and (
            not preserve_existing_structured or not existing_unit or force_override
        ):
            ent["unit"] = parsed["unit"]
        if parsed.get("reference_range") and (
            not preserve_existing_structured or not existing_range
        ):
            ent["reference_range"] = parsed["reference_range"]

        # Remove code snippets and bracketed ranges from display span.
        stripped = _READ_CODE_RE.sub(" ", original_text)
        stripped = _REF_RANGE_RE.sub(" ", stripped)
        stripped = _collapse_ws(stripped)

        value_span = parsed.get("value_span", "")
        interpretation_text: str | None = None
        interpretation_qualifier: str | None = None

        if value_span:
            value_pos = stripped.lower().find(value_span.lower())
            if value_pos > 0:
                before = stripped[:value_pos].strip(" -:;,")

                # Capture any trailing text AFTER the value span to detect
                # interpretation suffixes (e.g. "- Outside reference range").
                after_value = stripped[value_pos + len(value_span) :]
                interp = _detect_interpretation(after_value)
                if interp:
                    interpretation_text, interpretation_qualifier = interp

                # Drop a trailing current-value marker word ("now", "currently",
                # "today") so the entity text is not left with a dangling
                # connector after the post-marker value has been split off.
                before = _TRAILING_CURRENT_MARKER_RE.sub("", before).strip(" -:;,")
                stripped = _collapse_ws(before)
            elif value_pos == 0:
                after = stripped[len(value_span) :]
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
                    and _collapse_ws(str(e.get("text", ""))).lower().strip()
                    == value_span.lower().strip()
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

        # Emit interpretation phrase as a separate finding entity.
        # The SNOMED code for the finding is resolved downstream by the coding
        # resolver using /concepts/{observable_id}/related (INTERPRETS edges).
        if emit_interpretation_finding and interpretation_text:
            interp_start = _find_nearest_start(
                encounter_text,
                interpretation_text,
                around=int(ent.get("end", around) or around),
            )
            if interp_start is not None:
                duplicate = any(
                    str(e.get("label", "")) == "finding"
                    and str(e.get("interpretation_qualifier", ""))
                    == interpretation_qualifier
                    and str(e.get("parent_observable_text", "")) == stripped
                    for e in updated + extras
                )
                if not duplicate:
                    extras.append(
                        {
                            "text": interpretation_text,
                            "label": "finding",
                            "start": interp_start,
                            "end": interp_start + len(interpretation_text),
                            "confidence": float(ent.get("confidence", 0.0) or 0.0),
                            "interpretation_qualifier": interpretation_qualifier,
                            "parent_observable_text": stripped,
                        }
                    )

    if extras:
        updated.extend(extras)
    return updated
