"""Runtime recovery of missing lab procedure / observable / finding triples.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

This module is the runtime counterpart to ``libs/training/lab_span_detector.py``.
The training module proposes overlapping spans for gold-label backfill; this
module produces the SAME span shapes at inference time so the spancat model
no longer has to predict a 20+ token observable span on its own.

Why a separate module
---------------------
The spancat suggester in ``services/training_worker/app/config/base.cfg`` is
capped at ``max_size = 10`` tokens, which is shorter than the typical
``Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside
reference range`` line. Even after the cap is raised the model needs gold
data to learn from. Until both happen, the runtime model emits at most a
short procedure span (or nothing at all), the LLM extractor emits a short
``observable_entity`` for the parameter name only, and Layer 4 / Layer 6
of the post-processing stack have no long observable to enrich.

This recovery layer plugs the gap deterministically: when a line clearly
follows the UK primary-care lab grammar, it ADDS the missing
``procedure``, ``observable_entity`` and (when an interpretation phrase is
present) ``finding`` spans at the correct character offsets. It never
modifies or deletes existing entities.

Per ``.cursor/rules/dual-path-consistency.mdc``, this recovery is invoked
by ``libs/pipeline/post_processing.run_post_processing`` so both the
training verification path (``label_verifier``) and the runtime coding
path (``pipeline_service``) inherit the fix automatically.

Lenient mode
------------
Unlike ``lab_span_detector.detect_lab_pattern`` (which requires a Read
code in parens), this module also recovers triples on lab-shaped lines
that lack the bracketed code -- e.g.
``Atypical Lymphocytes: 0.70 x10^9/l; Outside reference range``. The
strict medical-unit whitelist from the training detector is reused so
the false-positive rate stays close to zero.

Parent design input: DI-LEO-AI-156.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from libs.training.lab_span_detector import (
    LABEL_FINDING,
    LABEL_OBSERVABLE,
    LABEL_PROCEDURE,
    _INTERP_RE,
    _KNOWN_UNIT_TOKENS,
    _RANGE_RE,
    _READ_CODE_RE,
    _UNIT_RE,
    _VALUE_RE,
    _looks_like_name_only_lab_procedure,
    _looks_like_medical_unit,
    _looks_like_prose,
)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Maximum number of characters in a single recovered observable span. Lines
# longer than this are skipped; they are almost always paragraphs rather
# than result rows.
_MAX_LINE_LENGTH = 240

# Maximum number of characters in the test-name prefix. Real lab names are
# 3-5 words ("Mean cell haemoglobin level"); anything much longer is prose.
_MAX_NAME_LENGTH = 80

# Token-boundary characters used to split the test name from the value.
# Lenient mode requires an EXPLICIT separator -- colon, semicolon, or
# whitespace-dash-whitespace. Bare whitespace-before-digit is intentionally
# excluded: free-form sentences like "eGFR 45 mL/min CKD stage 3" or
# "AMY on discharge was 145 U/L, trending down from 780 U/L" must not be
# auto-classified as lab triples because they typically contain extra
# clinical content the recovery would incorrectly absorb.
_NAME_VALUE_SPLIT_RE = re.compile(r"[:;]\s+|\s+-\s+")

# Marker that recovery added an entity. Downstream consumers (e.g. the
# gold-label review UI) can show a "needs review" chip on these.
_RECOVERY_MARKER = "_recovered_lab_triple"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LineHit:
    """One lab-shaped line found in the encounter text.

    All offsets are absolute (i.e. into the encounter_text), not line-relative.
    ``value_unit_end`` is the end of value + unit + optional [range] and
    NEVER includes the interpretation phrase. ``interpretation_end`` is the
    end of the interpretation phrase when ``has_interpretation`` is True;
    otherwise it equals ``value_unit_end``.
    """

    line_start: int
    line_end: int
    text: str
    name_start: int
    name_end: int
    value_unit_end: int
    interpretation_end: int
    has_interpretation: bool
    has_read_code: bool
    has_value_unit: bool = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def recover_lab_triples(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a new entity list with missing lab-triple spans appended.

    Pure: never mutates ``entities``. The returned list contains every
    input entity in original order, followed by zero or more recovered
    procedure / observable_entity / finding entities.

    Recovered entities carry ``_recovered_lab_triple = True`` so the
    gold-label UI can flag them for reviewer attention.
    """
    if not encounter_text:
        return list(entities)

    proposals = propose_lab_triples(encounter_text)
    if not proposals:
        return list(entities)

    existing_index = _index_existing_lab_spans(entities)
    additions: list[dict[str, Any]] = []

    for proposed in proposals:
        if not _is_duplicate(proposed, existing_index):
            additions.append(proposed)
            _register(proposed, existing_index)

    if not additions:
        return list(entities)
    return [*entities, *additions]


def propose_lab_triples(encounter_text: str) -> list[dict[str, Any]]:
    """Return deterministic lab-triple proposals for every lab hit."""

    if not encounter_text:
        return []
    hits = _scan_lab_lines(encounter_text)
    proposals: list[dict[str, Any]] = []
    for hit in hits:
        proposals.extend(_propose_for_hit(encounter_text, hit))
    return proposals


# ---------------------------------------------------------------------------
# Line scanning
# ---------------------------------------------------------------------------


def _iter_line_spans(text: str):
    """Yield (line_start, line_end, line_text) for every newline-separated line."""
    cursor = 0
    n = len(text)
    while cursor < n:
        nl = text.find("\n", cursor)
        if nl == -1:
            line_end = n
        else:
            line_end = nl
        yield cursor, line_end, text[cursor:line_end]
        if nl == -1:
            return
        cursor = nl + 1


def _scan_lab_lines(encounter_text: str) -> list[_LineHit]:
    """Find every line that matches the lab-result grammar (lenient)."""
    hits: list[_LineHit] = []
    for line_start, line_end, line_text in _iter_line_spans(encounter_text):
        if not line_text.strip():
            continue
        if _READ_CODE_RE.search(line_text):
            hits.extend(_scan_read_code_hits(line_start, line_end, line_text))
            continue
        if (line_end - line_start) > _MAX_LINE_LENGTH:
            continue
        hit = _try_parse_line(line_start, line_end, line_text)
        if hit is not None:
            hits.append(hit)
    return hits


def _scan_read_code_hits(
    line_start: int,
    line_end: int,
    line_text: str,
) -> list[_LineHit]:
    """Scan every Read-code observation inside a possibly long line."""

    matches = list(_READ_CODE_RE.finditer(line_text))
    hits: list[_LineHit] = []
    boundary = 0
    for index, match in enumerate(matches):
        segment_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(line_text)
        )
        hit = _parse_with_read_code(
            line_start,
            line_end,
            line_text,
            match,
            name_boundary=boundary,
            segment_end=segment_end,
        )
        if hit is None:
            boundary = max(boundary, match.end())
            continue
        hits.append(hit)
        boundary = max(boundary, hit.value_unit_end - line_start)
    return hits


def _try_parse_line(line_start: int, line_end: int, line_text: str) -> _LineHit | None:
    """Return a _LineHit if *line_text* looks like a lab result, else None."""
    code_match = _READ_CODE_RE.search(line_text)
    if code_match is not None:
        return _parse_with_read_code(line_start, line_end, line_text, code_match)
    return _parse_lenient_no_code(line_start, line_end, line_text)


def _parse_with_read_code(
    line_start: int,
    line_end: int,
    line_text: str,
    code_match: re.Match[str],
    *,
    name_boundary: int = 0,
    segment_end: int | None = None,
) -> _LineHit | None:
    """Parse a line with a Read/CTV3 code (the strict, high-precision path)."""
    code_start = code_match.start()
    code_end = code_match.end()

    name_start_in_line, name_str = _extract_read_code_name(
        line_text, name_boundary, code_start
    )
    if not name_str or _looks_like_prose(name_str):
        return None
    if len(name_str) > _MAX_NAME_LENGTH:
        return None

    name_start = line_start + name_start_in_line
    name_end = name_start + len(name_str)

    value_unit_end = _scan_value_unit(line_text, code_end)
    if value_unit_end is None:
        if _looks_like_name_only_lab_procedure(name_str):
            return _LineHit(
                line_start=line_start,
                line_end=line_start + code_end,
                text=line_text,
                name_start=name_start,
                name_end=name_end,
                value_unit_end=line_start + code_end,
                interpretation_end=line_start + code_end,
                has_interpretation=False,
                has_read_code=True,
                has_value_unit=False,
            )
        return None
    end_limit = segment_end if segment_end is not None else len(line_text)
    if value_unit_end > end_limit:
        return None
    interp_end, has_interp = _scan_interpretation(
        line_text, value_unit_end, segment_end=end_limit
    )

    return _LineHit(
        line_start=line_start,
        line_end=line_start + min(line_end - line_start, end_limit),
        text=line_text,
        name_start=name_start,
        name_end=name_end,
        value_unit_end=line_start + value_unit_end,
        interpretation_end=line_start + (interp_end if has_interp else value_unit_end),
        has_interpretation=has_interp,
        has_read_code=True,
    )


def _extract_read_code_name(
    line_text: str,
    boundary: int,
    code_start: int,
) -> tuple[int, str]:
    """Return the best lab-name suffix before a Read code."""

    raw = line_text[boundary:code_start]
    leading = len(raw) - len(raw.lstrip(" \t-:;,"))
    name_start = boundary + leading
    name = raw[leading:].rstrip(" -:;,\t")
    offset, trimmed = _trim_lab_name_prefix(name)
    return name_start + offset, trimmed


def _trim_lab_name_prefix(name: str) -> tuple[int, str]:
    """Remove appointment/prose prefixes while keeping the lab name."""

    stripped = name.strip()
    outer_offset = len(name) - len(name.lstrip())
    lowered = stripped.lower()
    for prefix in ("examination:", "objective:", "auto-filed"):
        idx = lowered.rfind(prefix)
        if idx != -1:
            start = idx + len(prefix)
            local = start + len(stripped[start:]) - len(stripped[start:].lstrip())
            return outer_offset + local, stripped[local:]
    double_space = list(re.finditer(r"\s{2,}", stripped))
    if double_space:
        local = double_space[-1].end()
        return outer_offset + local, stripped[local:]
    weight_note = re.match(r"\(\?[^)]{1,40}\)\s+", stripped)
    if weight_note is not None:
        return outer_offset + weight_note.end(), stripped[weight_note.end() :]
    oe_match = re.search(r"\bO/E\s+-\s+", stripped)
    if oe_match and oe_match.start() > 0:
        return outer_offset + oe_match.start(), stripped[oe_match.start() :]
    return outer_offset, stripped


def _parse_lenient_no_code(
    line_start: int, line_end: int, line_text: str
) -> _LineHit | None:
    """Parse a colon-, dash-, or whitespace-separated lab line without a Read code.

    Lenient mode accepts lab lines that lack the bracketed Read/CTV3 code.
    To keep false positives near zero we also reject:

    - test-name regions containing parentheses (drug brand names like
      "Amlodipine (Istin)" otherwise look like lab names without a code);
    - test-name regions containing common prescribing verbs ("prescribed",
      "given", "took", "started") which signal medication context, not labs.
    """
    split_match = _NAME_VALUE_SPLIT_RE.search(line_text)
    if split_match is None:
        return None

    name_str = line_text[: split_match.start()].rstrip(" -:;,\t")
    if not name_str or _looks_like_prose(name_str):
        return None
    if len(name_str) < 3 or len(name_str) > _MAX_NAME_LENGTH:
        return None
    if "(" in name_str or ")" in name_str:
        return None
    if _MEDICATION_CONTEXT_RE.search(name_str):
        return None

    name_start_in_line = len(line_text) - len(line_text.lstrip())
    name_start = line_start + name_start_in_line
    name_end = name_start + len(name_str)

    value_unit_end = _scan_value_unit(line_text, split_match.start())
    if value_unit_end is None:
        return None
    interp_end, has_interp = _scan_interpretation(line_text, value_unit_end)

    return _LineHit(
        line_start=line_start,
        line_end=line_end,
        text=line_text,
        name_start=name_start,
        name_end=name_end,
        value_unit_end=line_start + value_unit_end,
        interpretation_end=line_start + (interp_end if has_interp else value_unit_end),
        has_interpretation=has_interp,
        has_read_code=False,
    )


_MEDICATION_CONTEXT_RE = re.compile(
    r"\b(?:prescribed|given|took|takes|taking|started|stopped|"
    r"administered|dispensed|patient|reports|complains|history)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Value / unit / interpretation scanners (line-relative offsets)
# ---------------------------------------------------------------------------


def _scan_value_unit(line_text: str, start_at: int) -> int | None:
    """Return the line-relative end index just past value+unit (and optional range)."""
    tail = line_text[start_at:]
    if not tail.strip():
        return None

    leading_ws = len(tail) - len(tail.lstrip(" \t-:;,"))
    value_match = _VALUE_RE.match(tail.lstrip(" \t-:;,"))
    if value_match is None:
        return None

    cursor = start_at + leading_ws + value_match.end()
    unit_tail = line_text[cursor:]
    unit_ws = len(unit_tail) - len(unit_tail.lstrip(" \t"))
    cursor += unit_ws
    unit_match = _UNIT_RE.match(line_text[cursor:])
    if unit_match is None:
        return None
    if not _looks_like_medical_unit(unit_match.group(0)):
        return None
    cursor += unit_match.end()

    tail = line_text[cursor:]
    range_ws = len(tail) - len(tail.lstrip(" \t"))
    range_match = _RANGE_RE.match(line_text[cursor + range_ws :])
    if range_match is not None:
        cursor += range_ws + range_match.end()
    return cursor


def _scan_interpretation(
    line_text: str,
    start_at: int,
    *,
    segment_end: int | None = None,
) -> tuple[int, bool]:
    """Return (line-relative end, matched) just past the interpretation phrase."""
    tail = line_text[start_at:segment_end]
    match = _INTERP_RE.search(tail)
    if match is None:
        return start_at, False
    return start_at + match.end(), True


# ---------------------------------------------------------------------------
# Entity proposal
# ---------------------------------------------------------------------------


def _propose_for_hit(encounter_text: str, hit: _LineHit) -> list[dict[str, Any]]:
    """Return [procedure, observable_entity, finding?] for a single hit.

    The three spans are nested by design (see annotation guideline rules
    4 and 9):

    - procedure: just the test name
    - observable_entity: test name + value + unit + optional [range]
    - finding: the procedure span + value + unit + range + interpretation
    """
    proposals: list[dict[str, Any]] = []

    name_text = encounter_text[hit.name_start : hit.name_end]
    if name_text:
        proposals.append(
            _build_entity(LABEL_PROCEDURE, hit.name_start, hit.name_end, name_text)
        )

    obs_end = min(hit.value_unit_end, hit.line_end)
    obs_text = encounter_text[hit.name_start : obs_end].rstrip()
    if obs_text and obs_end > hit.name_end and hit.has_value_unit:
        proposals.append(
            _build_entity(
                LABEL_OBSERVABLE,
                hit.name_start,
                hit.name_start + len(obs_text),
                obs_text,
            )
        )

    if hit.has_interpretation:
        finding_end = min(hit.interpretation_end, hit.line_end)
        finding_text = encounter_text[hit.name_start : finding_end].rstrip()
        if finding_text:
            proposals.append(
                _build_entity(
                    LABEL_FINDING,
                    hit.name_start,
                    hit.name_start + len(finding_text),
                    finding_text,
                )
            )

    return proposals


def _build_entity(label: str, start: int, end: int, text: str) -> dict[str, Any]:
    return {
        "text": text,
        "label": label,
        "semantic_tag": label,
        "start": start,
        "end": end,
        "assertion": "present",
        "confidence": 0.0,
        _RECOVERY_MARKER: True,
    }


# ---------------------------------------------------------------------------
# Duplicate suppression
# ---------------------------------------------------------------------------


_LAB_LABELS = frozenset({LABEL_PROCEDURE, LABEL_OBSERVABLE, LABEL_FINDING})


def _index_existing_lab_spans(
    entities: list[dict[str, Any]],
) -> dict[str, set[tuple[int, int]]]:
    """Map label -> set of (start, end) spans already present."""
    index: dict[str, set[tuple[int, int]]] = {label: set() for label in _LAB_LABELS}
    for ent in entities:
        label = _normalise_label(str(ent.get("label", "")))
        if label not in _LAB_LABELS:
            continue
        try:
            start = int(ent.get("start", 0))
            end = int(ent.get("end", 0))
        except (TypeError, ValueError):
            continue
        index[label].add((start, end))
    return index


def _normalise_label(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def _is_duplicate(
    proposed: dict[str, Any],
    existing_index: dict[str, set[tuple[int, int]]],
) -> bool:
    label = _normalise_label(str(proposed.get("label", "")))
    span = (int(proposed["start"]), int(proposed["end"]))
    return span in existing_index.get(label, set())


def _register(
    proposed: dict[str, Any],
    existing_index: dict[str, set[tuple[int, int]]],
) -> None:
    label = _normalise_label(str(proposed.get("label", "")))
    span = (int(proposed["start"]), int(proposed["end"]))
    existing_index.setdefault(label, set()).add(span)


__all__ = [
    "propose_lab_triples",
    "recover_lab_triples",
]


# Re-export the strict whitelist for tests that want to assert the unit
# guard remains conservative without importing from the training module.
KNOWN_UNIT_TOKENS = _KNOWN_UNIT_TOKENS
