"""Canonical surface-form normalisation for SNOMED resolution.

Atlas trace:
  DO: DO-8C497D0C
  DI: DI-82036B4D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8C497D0C")

Two functions are exported:

``normalize_surface(text)``
    Lowercase, tokenise, collapse whitespace. Must match the exact-match key
    used by CodingResolver.

``strip_observable_value(text)``
    Remove embedded numeric value+unit from a lab-result phrase so the clean
    test name can be used as a surface form.

    Examples:
        'Serum albumin 40 g/L'        -> 'Serum albumin'
        'Haemoglobin A1c 57 mmol/mol' -> 'Haemoglobin A1c'
        'MCH 30.4 pg'                 -> 'MCH'
        'Platelet count 312 10^9/L'   -> 'Platelet count'
        'eGFR >90 mL/min'             -> 'eGFR'
        'Chest pain'                  -> 'Chest pain'  (unchanged, no unit)

    The logic mirrors ``observable_post_processor.normalize_observable_entities``
    which strips values from entity span text at runtime. This function is the
    equivalent normalisation step for surface-form candidates that come from
    stored ``r.evidence`` values in Neo4j (which may pre-date the runtime
    stripping).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# normalize_surface
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
TOKEN_RE = _TOKEN_RE  # public alias for callers that import TOKEN_RE directly


def normalize_surface(text: str) -> str:
    """Return a lowercase token-joined form for exact-match lookup."""
    if not text:
        return ""
    return " ".join(_TOKEN_RE.findall(text.lower()))


# ---------------------------------------------------------------------------
# strip_observable_value
# ---------------------------------------------------------------------------

_READ_CODE_RE = re.compile(r"\([A-Za-z0-9]{3,8}\.{0,2}\)")
_REF_RANGE_RE = re.compile(r"\[(?P<range>[^\]]+)\]")
_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*(?:\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?))\s*"
    r"(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)
_KNOWN_UNIT_RE = re.compile(
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|ml|l|fl|%|mmhg|kpa|bpm|miu|u/l|g/l|10\^)",
    re.IGNORECASE,
)


def strip_observable_value(text: str) -> str:
    """Strip embedded numeric value+unit from a lab-result evidence phrase.

    Returns the text unchanged if no plausible value+unit pattern is found
    (i.e. safe to call on any evidence string -- non-lab phrases are returned
    as-is).

    This function has no side effects and is idempotent: calling it twice on
    an already-stripped phrase returns the same phrase.
    """
    if not text:
        return text
    searchable = _READ_CODE_RE.sub(" ", text)
    searchable = _REF_RANGE_RE.sub(" ", searchable)
    matches = list(_VALUE_UNIT_RE.finditer(searchable))
    if not matches:
        return text
    plausible = [m for m in matches if _KNOWN_UNIT_RE.search(m.group("unit") or "")]
    if not plausible:
        return text
    match = plausible[-1]
    if match.start() > 0:
        before = text[: match.start()].strip(" -:;,")
        if before:
            return re.sub(r"\s+", " ", before).strip()
    return text
