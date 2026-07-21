"""Pure scanner for observation-threshold findings in clinical text.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Atlas trace (Phase 6):
    UN: UN-26E57FA1
    DI: DI-4C8A09C3
    DO: DO-CB6324A3
    VT: VT-1A7862B9 (execution_status=passed)

Extracted from ``scripts/atlas/backfill_observation_leaves.py`` so
the CLI script stays under the 500 LOC file limit and so unit tests
can exercise the regex + alias index without pulling in Neo4j or the
argparse entrypoint.

Responsibility: given a block of ``Recommendation.verbatim`` text,
yield every numeric threshold on a known observable. Does NOT touch
Neo4j and does NOT mutate rule logic.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator

from libs.units.observable_units import (
    UnitConversionError,
    OBSERVABLE_UNIT_REGISTRY,
    canonicalise_value,
    is_known_observable,
    known_aliases,
)

logger = logging.getLogger(__name__)

#: Prefix operator words: "<op> <value>" e.g. "less than 60".
_OPERATOR_MAP = {
    ">=": ">=",
    ">": ">",
    "<=": "<=",
    "<": "<",
    "=": "=",
    "at or above": ">=",
    "or above": ">=",
    "at least": ">=",
    "above": ">",
    "greater than": ">",
    "more than": ">",
    "at or below": "<=",
    "or below": "<=",
    "below": "<",
    "less than": "<",
    "under": "<",
}

#: Postfix operator words: "<value> <postop>" e.g. "400 x10*9/L or more".
_POSTFIX_OPERATOR_MAP = {
    "or more": ">=",
    "or higher": ">=",
    "or greater": ">=",
    "or above": ">=",
    "and above": ">=",
    "or less": "<=",
    "or lower": "<=",
    "or below": "<=",
    "and below": "<=",
}

#: Common clinical abbreviations NICE uses interchangeably with the
#: full display names in OBSERVABLE_UNIT_REGISTRY. The registry itself
#: only lists UCUM unit aliases; this map supplements it so the
#: scanner can find "eGFR" or "PSA" in source text.
_OBSERVABLE_NAME_EXTRA_ALIASES: dict[str, list[str]] = {
    "365632008": ["platelets", "plt"],
    "441689006": ["hb", "hgb", "haemoglobin"],
    "1003671000000109": ["hba1c", "glycated haemoglobin", "a1c"],
    "1011481000000105": ["egfr", "gfr", "estimated glomerular filtration rate"],
    "113075003": ["creatinine", "serum creatinine"],
    "1017401000000100": ["alt", "alanine transaminase"],
    "167271000": ["ferritin", "serum ferritin"],
    "313730000": ["psa", "serum psa", "prostate-specific antigen"],
    "271649006": ["systolic bp", "sbp"],
    "271650006": ["diastolic bp", "dbp"],
    "27113001": ["weight", "bodyweight"],
    "60621009": ["bmi", "body-mass index"],
}

_NUMBER = r"[0-9]+(?:\.[0-9]+)?"
_UNIT_CHARS = r"[A-Za-z0-9\u00b5\u03bc*/().\^_\-\[\]{}]+"
_CONNECTOR = r"(?:\s+(?:of|is|at|level of|reading of))?"
_OPERATOR_ALT = "|".join(
    re.escape(k) for k in sorted(_OPERATOR_MAP, key=len, reverse=True)
)
_POSTFIX_OPERATOR_ALT = "|".join(
    re.escape(k) for k in sorted(_POSTFIX_OPERATOR_MAP, key=len, reverse=True)
)

_THRESHOLD_RE = re.compile(
    r"(?P<observable>[A-Za-z][A-Za-z0-9 \-]{0,80}?)"
    + _CONNECTOR
    + r"\s+(?P<operator>" + _OPERATOR_ALT + r")\s+"
    r"(?P<value>" + _NUMBER + r")"
    r"(?:\s*(?P<unit>" + _UNIT_CHARS + r"))?",
    re.IGNORECASE,
)

_POSTFIX_THRESHOLD_RE = re.compile(
    r"(?P<observable>[A-Za-z][A-Za-z0-9 \-]{0,80}?)"
    + _CONNECTOR
    + r"\s+(?P<value>" + _NUMBER + r")"
    r"(?:\s*(?P<unit>" + _UNIT_CHARS + r"))?\s+"
    r"(?P<operator>" + _POSTFIX_OPERATOR_ALT + r")",
    re.IGNORECASE,
)

_BETWEEN_RE = re.compile(
    r"(?P<observable>[A-Za-z][A-Za-z0-9 \-]{0,80}?)"
    + _CONNECTOR
    + r"\s+between\s+"
    r"(?P<low>" + _NUMBER + r")\s+and\s+"
    r"(?P<high>" + _NUMBER + r")"
    r"(?:\s*(?P<unit>" + _UNIT_CHARS + r"))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ThresholdFinding:
    """A single candidate observation threshold extracted from text."""

    observable_id: str
    observable_term: str
    operator: str
    value: float | list[float]
    unit_authored: str
    unit_canonical: str
    value_canonical: float | list[float]
    source_sentence: str


def build_alias_index() -> dict[str, tuple[str, str]]:
    """Return a lowercase alias -> (observable_id, display_name) lookup.

    Combines the registry's own UCUM + display aliases with the local
    ``_OBSERVABLE_NAME_EXTRA_ALIASES`` clinical abbreviations.
    """
    index: dict[str, tuple[str, str]] = {}
    for obs_id, spec in OBSERVABLE_UNIT_REGISTRY.items():
        display = spec.display_name
        for alias in known_aliases(obs_id):
            alias_low = alias.lower().strip()
            if alias_low and alias_low not in index:
                index[alias_low] = (obs_id, display)
        display_low = display.lower().strip()
        if display_low and display_low not in index:
            index[display_low] = (obs_id, display)
        for extra in _OBSERVABLE_NAME_EXTRA_ALIASES.get(obs_id, []):
            extra_low = extra.lower().strip()
            if extra_low and extra_low not in index:
                index[extra_low] = (obs_id, display)
    return index


def match_observable(
    text: str, alias_index: dict[str, tuple[str, str]]
) -> tuple[str, str] | None:
    """Return (observable_id, display) for the rightmost alias hit in ``text``.

    Tokens split on whitespace; we try progressively longer right-
    anchored spans -- "egfr" first, then "with egfr", and so on --
    until we find an alias or exhaust the phrase. Mirrors how the
    editor renders the observable (the rightmost meaningful noun).
    """
    low = " ".join(text.lower().split())
    if not low:
        return None
    if low in alias_index:
        return alias_index[low]
    tokens = low.split(" ")
    for start in range(len(tokens)):
        candidate = " ".join(tokens[start:]).strip()
        if candidate and candidate in alias_index:
            return alias_index[candidate]
    return None


def sentence_window(text: str, start: int, end: int) -> str:
    """Trim ``text`` to the sentence containing ``[start:end]`` for reporting."""
    before = text.rfind(".", 0, start) + 1
    after = text.find(".", end)
    if after == -1:
        after = len(text)
    return text[before:after].strip()


def default_within_days(observable_id: str) -> int:
    """Seed recency window: 90 days for vitals, 365 days for labs."""
    if not is_known_observable(observable_id):
        return 365
    term = OBSERVABLE_UNIT_REGISTRY[observable_id].display_name.lower()
    if any(
        tag in term
        for tag in ("blood pressure", "weight", "body mass index", "bmi")
    ):
        return 90
    return 365


_TRAILING_PUNCT = ".,;:!?"


def _strip_trailing_punct(unit: str) -> str:
    """Strip trailing sentence punctuation from a unit token.

    The regex intentionally allows dots inside units (e.g.
    ``mL/min/1.73m2``), which means a unit captured at the end of a
    sentence can keep the full-stop. Canonicalisation will fail for
    ``mL/min/1.73m2.`` so we try stripping the trailing punctuation
    and re-canonicalising before giving up.
    """
    trimmed = unit
    while trimmed and trimmed[-1] in _TRAILING_PUNCT:
        trimmed = trimmed[:-1]
    return trimmed


def _canonicalise(
    obs_id: str, value: float, unit: str
) -> tuple[float, str] | None:
    """Canonicalise ``value`` in ``unit`` to the observable's canonical unit.

    Returns ``(canonical_value, unit_used)`` so the caller can keep
    the trimmed unit on the ThresholdFinding, or ``None`` when no
    conversion is available after sentence-punctuation stripping.
    """
    for candidate in (unit, _strip_trailing_punct(unit)):
        if not candidate:
            continue
        try:
            return canonicalise_value(obs_id, value, candidate), candidate
        except (UnitConversionError, ValueError):
            continue
    logger.warning(
        "Could not canonicalise %r %s for %s (tried '%s' and '%s')",
        value,
        unit,
        obs_id,
        unit,
        _strip_trailing_punct(unit),
    )
    return None


def _emit_between(
    m: re.Match[str],
    verbatim: str,
    alias_index: dict[str, tuple[str, str]],
) -> ThresholdFinding | None:
    match = match_observable(m.group("observable"), alias_index)
    if not match:
        return None
    obs_id, term = match
    unit = (m.group("unit") or "").strip()
    if not unit:
        return None
    low_raw = float(m.group("low"))
    high_raw = float(m.group("high"))
    low_result = _canonicalise(obs_id, low_raw, unit)
    high_result = _canonicalise(obs_id, high_raw, unit)
    if low_result is None or high_result is None:
        return None
    low_canon, used_unit = low_result
    high_canon, _ = high_result
    return ThresholdFinding(
        observable_id=obs_id,
        observable_term=term,
        operator="between",
        value=[low_raw, high_raw],
        unit_authored=used_unit,
        unit_canonical=OBSERVABLE_UNIT_REGISTRY[obs_id].canonical_unit,
        value_canonical=[low_canon, high_canon],
        source_sentence=sentence_window(verbatim, m.start(), m.end()),
    )


def _emit_scalar(
    m: re.Match[str],
    op: str,
    verbatim: str,
    alias_index: dict[str, tuple[str, str]],
) -> ThresholdFinding | None:
    match = match_observable(m.group("observable"), alias_index)
    if not match:
        return None
    obs_id, term = match
    unit = (m.group("unit") or "").strip()
    if not unit:
        return None
    raw = float(m.group("value"))
    result = _canonicalise(obs_id, raw, unit)
    if result is None:
        return None
    canon, used_unit = result
    return ThresholdFinding(
        observable_id=obs_id,
        observable_term=term,
        operator=op,
        value=raw,
        unit_authored=used_unit,
        unit_canonical=OBSERVABLE_UNIT_REGISTRY[obs_id].canonical_unit,
        value_canonical=canon,
        source_sentence=sentence_window(verbatim, m.start(), m.end()),
    )


def iter_findings(
    verbatim: str, alias_index: dict[str, tuple[str, str]]
) -> Iterator[ThresholdFinding]:
    """Yield every threshold finding we recognise in ``verbatim``.

    Dedupe: when two regex patterns overlap on the same span, the
    first-priority pattern (between > postfix > prefix) wins so we do
    not double-count the same clinical threshold.
    """
    if not verbatim:
        return
    claimed: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in claimed)

    for m in _BETWEEN_RE.finditer(verbatim):
        finding = _emit_between(m, verbatim, alias_index)
        if finding:
            claimed.append((m.start(), m.end()))
            yield finding
    for m in _POSTFIX_THRESHOLD_RE.finditer(verbatim):
        if _overlaps(m.start(), m.end()):
            continue
        op = _POSTFIX_OPERATOR_MAP.get(m.group("operator").lower())
        if not op:
            continue
        finding = _emit_scalar(m, op, verbatim, alias_index)
        if finding:
            claimed.append((m.start(), m.end()))
            yield finding
    for m in _THRESHOLD_RE.finditer(verbatim):
        if _overlaps(m.start(), m.end()):
            continue
        op = _OPERATOR_MAP.get(m.group("operator").lower())
        if not op:
            continue
        finding = _emit_scalar(m, op, verbatim, alias_index)
        if finding:
            claimed.append((m.start(), m.end()))
            yield finding
