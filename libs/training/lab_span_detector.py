"""Detect lab-result text and plan the procedure / observable / finding triple.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Applies to gold-label training text that follows the standard UK primary-care
lab-result grammar, e.g.

    Reticulocyte count (42X..) 62 10^9/L [20 - 80]
    Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] - Outside reference range
    Serum vitamin D level (XE2e7) 64 nmol/L
    Atypical Lymphocytes: 0.70 x10^9/l; Outside reference range

For each record we propose up to three overlapping spans, in line with the
annotation guideline (rules 4 and 9, `libs/prompts/annotation_guidelines_v1.py`):

1. ``procedure`` - the short test-name span (kept for the existing Read-code
   procedure coding).
2. ``observable_entity`` - the test-name + value + unit span (the measurement).
3. ``finding`` - the full sentence, only when an interpretation phrase is
   present (e.g. "Outside reference range", "Abnormal", "Detected").

Backfill is additive: existing entities are never modified or removed, only
missing overlapping spans are proposed. Proposed spans carry no SNOMED code;
reviewers fill those in through the normal gold-dataset editor. See
``DI-LEO-AI-054`` (training label auditor) for the parent design input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# -- Regex building blocks ----------------------------------------------------

# Read-code / CTV3 bracketed code, e.g. "(42X..)", "(XE2pb)", "(X772q)".
# Real Read / CTV3 codes always contain at least one digit; requiring this
# rejects drug brand names in parens (e.g. "(Fermagon)") that would otherwise
# be misread as a code.
_READ_CODE_RE = re.compile(
    r"\((?=[A-Za-z0-9.]{3,8}\))([A-Za-z0-9.]*[0-9][A-Za-z0-9.]*)\)"
)

# Numeric value token: "62", "0.70", "<5", "< 5", "5.6".
_VALUE_RE = re.compile(r"[<>]?\s*\d+(?:\.\d+)?")

# A unit token: letters, digits, %, /, ^, * - but not brackets/whitespace.
# Real examples seen in gold data:
#   10^9/L, x10^9/l, nmol/L, g/L, mg/L, umol/L, pg, fL, %, u/mL, iu/mL,
#   degC, Kg/m.
_UNIT_RE = re.compile(r"[A-Za-z0-9%/^*]+")

# Strict medical-unit whitelist. A unit must either contain '/', '^', '%',
# 'x10' (as in x10^9), OR be a short token recognised as a UK primary-care
# lab unit. Words like "ductal", "grade", "moderate", "ER+ve" do not match.
_KNOWN_UNIT_TOKENS: frozenset[str] = frozenset({
    # volume / concentration
    "nmol", "umol", "mmol", "mol", "mcg", "meq", "miu",
    "ng", "pg", "fg", "ug", "mg", "g", "kg",
    "fl", "pl", "ul", "ml", "dl", "l", "cl",
    # count / international
    "iu", "u", "cells", "copies",
    # dimensional / physical
    "pct", "percent", "bpm", "mmhg", "kpa",
    "cm", "mm", "m", "kgm",
    "degc", "degf", "c", "f",
    # time / rate
    "min", "hr", "sec", "s",
})


def _looks_like_medical_unit(token: str) -> bool:
    """Accept only tokens that are unambiguously medical units.

    Pure-number tokens, prose words, and words lacking any unit signature
    are rejected to keep the backfill detector conservative.
    """
    if not token:
        return False
    lower = token.lower()
    if "/" in lower or "^" in lower or "%" in lower:
        return any(ch.isalpha() or ch in "%/^" for ch in lower)
    if lower.startswith("x10"):
        return True
    return lower in _KNOWN_UNIT_TOKENS


# Reference range, e.g. "[20 - 80]", "[< 21]", "[0.78 - 2]".
_RANGE_RE = re.compile(r"\[[^\]]{1,40}\]")

# Between the Read-code close and the numeric value, only whitespace is
# allowed. A dash ("Xa3eQ - L") or a colon is a strong signal that the text
# is not a lab result but a disorder / finding with a qualifier.
_POST_CODE_TO_VALUE_RE = re.compile(
    r"^[ \t]+(?=[<>]?[ \t]*\d)"
)

# Prose prefixes that must never be treated as a lab test name.
_PROSE_PREFIXES: tuple[str, ...] = (
    "problem",
    "major",
    "history",
    "complaint",
    "issue",
    "diagnosis",
    "impression",
    "plan",
    "assessment",
    "reason",
    "episode",
    "note",
)

# Interpretation phrases that follow a lab value. Case-insensitive.
_INTERP_PATTERNS: tuple[str, ...] = (
    r"outside reference range",
    r"abnormal[^,;.\n]*",
    r"not detected[^,;.\n]*",
    r"detected by[^,;.\n]*",
    r"satisfactory[^,;.\n]*",
    r"no further action[^,;.\n]*",
    r"within reference range",
    r"within normal limits",
    r"low",
    r"high",
    r"raised",
    r"elevated",
)
_INTERP_RE = re.compile(
    r"(?:[-,;]\s*)(" + "|".join(_INTERP_PATTERNS) + r")",
    re.IGNORECASE,
)

# Labels we care about. Keep lower-case; the export layer upper-cases them.
LABEL_PROCEDURE = "procedure"
LABEL_OBSERVABLE = "observable_entity"
LABEL_FINDING = "finding"

_LAB_LABELS: frozenset[str] = frozenset({
    LABEL_PROCEDURE,
    LABEL_OBSERVABLE,
    LABEL_FINDING,
})


@dataclass
class LabSpan:
    """One proposed or existing span on a lab record."""

    label: str
    start: int
    end: int
    text: str


@dataclass
class LabPattern:
    """Result of parsing a lab-result sentence.

    ``matched`` is False when the text does not look like a lab result. In
    that case no spans are proposed.
    """

    matched: bool
    test_name_span: LabSpan | None = None
    observable_span: LabSpan | None = None
    finding_span: LabSpan | None = None
    has_interpretation: bool = False
    has_value_unit: bool = False
    read_code: str | None = None


@dataclass
class BackfillPlan:
    """Entities that should be added to bring a record up to the guideline.

    ``existing_labels`` records which of the three lab labels were already
    present in the input. ``proposed`` is the list of entity dicts to append
    (without SNOMED codes).
    """

    matched: bool
    existing_labels: set[str] = field(default_factory=set)
    proposed: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


# -- Public API ---------------------------------------------------------------


def detect_lab_pattern(text: str) -> LabPattern:
    """Return the structural spans for a lab-result sentence, or empty match.

    We require BOTH a Read-code / CTV3 bracketed code AND a value+unit token
    to treat the text as a lab result. This is strict on purpose: the gold
    corpus contains many prose sentences with colons or stray numbers, and
    over-matching them would propose incorrect spans on non-lab records.

    The rare "colon-separated without Read code" variant is explicitly
    excluded to keep the false-positive rate at zero for the backfill.
    """
    if not text or not text.strip():
        return LabPattern(matched=False)

    code_start, code_end, read_code = _find_read_code(text)
    if read_code is None:
        return LabPattern(matched=False)

    name_start, name_end = 0, code_start
    test_name = text[name_start:name_end].strip()
    if not test_name or _looks_like_prose(test_name):
        return LabPattern(matched=False)

    leading_ws = len(text[name_start:name_end]) - len(
        text[name_start:name_end].lstrip()
    )
    test_name_start = name_start + leading_ws
    test_name_end = test_name_start + len(test_name)

    # Require value to appear IMMEDIATELY after the Read-code close, separated
    # only by whitespace. Anything else ("- L", ": Stage IIIa", "; x10") is
    # almost always a disorder/procedure qualifier rather than a lab value.
    if _POST_CODE_TO_VALUE_RE.match(text[code_end:]) is None:
        return LabPattern(matched=False)

    value_end, has_value_unit = _find_value_unit_end(text, start_at=code_end)
    interp_end, has_interp = _find_interpretation_end(text, start_at=value_end)

    if not has_value_unit:
        # Without an unambiguous medical value+unit we do not propose spans.
        return LabPattern(matched=False)

    procedure_span = LabSpan(
        LABEL_PROCEDURE, test_name_start, test_name_end, test_name
    )

    observable_span = None
    if has_value_unit:
        obs_end = max(value_end, test_name_end)
        obs_text = text[test_name_start:obs_end].strip()
        if obs_text:
            observable_span = LabSpan(
                LABEL_OBSERVABLE, test_name_start, test_name_start + len(obs_text),
                obs_text,
            )

    finding_span = None
    if has_interp:
        find_end = max(interp_end, value_end, test_name_end)
        find_text = text[test_name_start:find_end].strip()
        if find_text:
            finding_span = LabSpan(
                LABEL_FINDING, test_name_start, test_name_start + len(find_text),
                find_text,
            )

    return LabPattern(
        matched=True,
        test_name_span=procedure_span,
        observable_span=observable_span,
        finding_span=finding_span,
        has_interpretation=has_interp,
        has_value_unit=has_value_unit,
        read_code=read_code,
    )


def plan_triple_backfill(
    text: str, entities: list[dict[str, Any]]
) -> BackfillPlan:
    """Return the entities to ADD to achieve the lab-triple guideline.

    Only proposes overlapping spans that the reviewer has not already
    labelled. Never returns an entity dict that overlaps an existing entity
    with the same label.
    """
    pattern = detect_lab_pattern(text)
    if not pattern.matched or pattern.test_name_span is None:
        return BackfillPlan(matched=False, reason="no_lab_pattern")

    existing_labels, existing_by_label = _summarise_existing_lab_entities(
        entities
    )

    # A bare "Reticulocyte count" sentence only needs the procedure label;
    # there is nothing to backfill toward observable / finding.
    if not pattern.has_value_unit and not pattern.has_interpretation:
        return BackfillPlan(
            matched=True,
            existing_labels=existing_labels,
            reason="name_only",
        )

    proposed: list[dict[str, Any]] = []

    if LABEL_PROCEDURE not in existing_labels:
        proposed.append(_span_to_entity(pattern.test_name_span))

    if (
        pattern.observable_span is not None
        and LABEL_OBSERVABLE not in existing_labels
    ):
        proposed.append(_span_to_entity(pattern.observable_span))

    if (
        pattern.finding_span is not None
        and LABEL_FINDING not in existing_labels
    ):
        proposed.append(_span_to_entity(pattern.finding_span))

    # Drop any proposal that exactly duplicates an existing entity span.
    proposed = _drop_exact_duplicates(proposed, existing_by_label)

    reason = "complete" if not proposed else "backfill_needed"
    return BackfillPlan(
        matched=True,
        existing_labels=existing_labels,
        proposed=proposed,
        reason=reason,
    )


def diagnose_lab_triple_coverage(
    text: str, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """Lightweight diagnostic for the UI and dataset-health panel.

    Returns a dict with ``is_lab`` (bool), ``missing`` (list of labels),
    ``has_interpretation`` (bool). Does not propose concrete spans.
    """
    pattern = detect_lab_pattern(text)
    if not pattern.matched:
        return {
            "is_lab": False,
            "missing": [],
            "has_interpretation": False,
            "has_value_unit": False,
        }

    existing_labels, _ = _summarise_existing_lab_entities(entities)
    missing: list[str] = []

    if LABEL_PROCEDURE not in existing_labels:
        missing.append(LABEL_PROCEDURE)
    if pattern.has_value_unit and LABEL_OBSERVABLE not in existing_labels:
        missing.append(LABEL_OBSERVABLE)
    if pattern.has_interpretation and LABEL_FINDING not in existing_labels:
        missing.append(LABEL_FINDING)

    return {
        "is_lab": True,
        "missing": missing,
        "has_interpretation": pattern.has_interpretation,
        "has_value_unit": pattern.has_value_unit,
        "read_code": pattern.read_code,
    }


# -- Internals ----------------------------------------------------------------


def _find_read_code(text: str) -> tuple[int, int, str | None]:
    """Return (start, end, code) of the first Read-code bracket, or (-1,-1,None)."""
    match = _READ_CODE_RE.search(text)
    if match is None:
        return -1, -1, None
    return match.start(), match.end(), match.group(1)


_COLON_OR_VALUE_RE = re.compile(r"[:\s]+[<>]?\s*\d")


def _find_name_before_colon_or_value(text: str) -> tuple[int, int]:
    """Find the test-name span when no Read code is present.

    Uses a colon or the first numeric value as the boundary, e.g.
    "Atypical Lymphocytes: 0.70 x10^9/l".
    """
    match = _COLON_OR_VALUE_RE.search(text)
    if match is None:
        return 0, 0
    end = match.start()
    # Strip any trailing colon/whitespace from the name.
    while end > 0 and text[end - 1] in ": \t":
        end -= 1
    return 0, end


_PROSE_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "or", "but", "if", "then", "a", "an",
    "patient", "reports", "complaining", "history", "of",
})


def _looks_like_prose(test_name: str) -> bool:
    """Reject obvious free-text prose (simple heuristic)."""
    tokens = [tok.lower() for tok in test_name.split() if tok]
    if not tokens:
        return True
    # Prose prefixes like "Problem:", "Major:", "History:" are never lab
    # test names in the UK primary-care gold corpus.
    first = tokens[0].rstrip(":.,;")
    if first in _PROSE_PREFIXES:
        return True
    if len(tokens) > 8:
        return True
    stopword_hits = sum(1 for tok in tokens if tok in _PROSE_STOPWORDS)
    return stopword_hits >= 2


def _find_value_unit_end(text: str, *, start_at: int) -> tuple[int, bool]:
    """Return (end_index, matched) just past the value+unit (and optional range).

    Requires a numeric value at the start of the tail (allowing only leading
    whitespace) AND a whitelisted medical unit immediately after. Without a
    medical unit the match fails, so prose containing stray numbers does not
    accidentally trigger.
    """
    tail = text[start_at:]
    if not tail.strip():
        return start_at, False

    value_match = _VALUE_RE.match(tail.lstrip(" \t"))
    if value_match is None:
        return start_at, False

    value_offset = len(tail) - len(tail.lstrip(" \t"))
    cursor = start_at + value_offset + value_match.end()
    unit_tail = text[cursor:]
    leading_ws = len(unit_tail) - len(unit_tail.lstrip(" \t"))
    cursor += leading_ws
    unit_match = _UNIT_RE.match(text[cursor:])
    if unit_match is None or not _looks_like_medical_unit(unit_match.group(0)):
        return start_at, False

    cursor += unit_match.end()

    # Optional reference range directly after the unit.
    tail = text[cursor:]
    leading_ws = len(tail) - len(tail.lstrip(" \t"))
    range_match = _RANGE_RE.match(text[cursor + leading_ws:])
    if range_match is not None:
        cursor += leading_ws + range_match.end()
    return cursor, True


def _find_interpretation_end(
    text: str, *, start_at: int
) -> tuple[int, bool]:
    """Return (end_index, matched) just past the interpretation phrase."""
    tail = text[start_at:]
    match = _INTERP_RE.search(tail)
    if match is None:
        return start_at, False
    return start_at + match.end(), True


def _summarise_existing_lab_entities(
    entities: list[dict[str, Any]],
) -> tuple[set[str], dict[str, list[tuple[int, int, str]]]]:
    """Collect existing lab-label presence and (start,end,text) tuples."""
    labels: set[str] = set()
    by_label: dict[str, list[tuple[int, int, str]]] = {}
    for ent in entities:
        raw = str(ent.get("label") or ent.get("semantic_tag") or "").strip().lower()
        raw = raw.replace(" ", "_")
        if raw not in _LAB_LABELS:
            continue
        labels.add(raw)
        try:
            start = int(ent.get("start", 0))
            end = int(ent.get("end", 0))
        except (TypeError, ValueError):
            start, end = 0, 0
        by_label.setdefault(raw, []).append(
            (start, end, str(ent.get("text", "")))
        )
    return labels, by_label


def _span_to_entity(span: LabSpan) -> dict[str, Any]:
    return {
        "text": span.text,
        "start": span.start,
        "end": span.end,
        "label": span.label,
        "semantic_tag": span.label,
        "assertion": "present",
        "snomed_concept_id": "",
        "snomed_term": "",
        "_backfilled": True,
    }


def _drop_exact_duplicates(
    proposed: list[dict[str, Any]],
    existing_by_label: dict[str, list[tuple[int, int, str]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ent in proposed:
        label = str(ent.get("label", "")).lower()
        existing = existing_by_label.get(label, [])
        start = int(ent.get("start", 0))
        end = int(ent.get("end", 0))
        if any(s == start and e == end for s, e, _ in existing):
            continue
        out.append(ent)
    return out
