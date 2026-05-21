"""Shared term normalisation helpers for extraction surface forms.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B5C78811
  DO: DO-728930A1
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B5C78811")

Provides deterministic, environment-agnostic cleanup for extracted clinical
terms so the runtime coding pipeline and the validation scoring path apply
exactly one cleanup rule set. Validation-specific helpers (case-bound alias
maps, fixture-noise markers) stay in the scorer; everything here is safe to
run on production output.

Layer 4b ("Observable Surface Cleanup") in
``libs/pipeline/post_processing.py`` calls ``clean_observable_surface_text``
on every observable_entity span so downstream stringification matches what
the validation scorer would compute.
"""

from __future__ import annotations

import re

# Match a trailing value+unit (optionally with a reference range parens block)
# attached to an observable surface form, e.g. "Haemoglobin 124 g/L (115-160)".
# The leading "[:=-]?" tolerates the various separators EHR templates use.
VALUE_UNIT_TAIL_RE = re.compile(
    r"""
    \s*[:=-]?\s*
    [<>]?\d+(?:\.\d+)?\s*
    (?:
      x10\^?\d+/?l|
      mmol/?l|
      umol/?l|
      g/?l|
      ug/?l|
      mg/?l|
      ng/?ml|
      iu/?l|
      u/?l|
      ml/?min(?:/1\.73m2)?|
      f(?:l|L)|
      pg|
      %
    )
    (?:\s*\([^)]*\))?
    [\s.,;:]*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Pure numeric tokens like "5.2", "<10", "120/80" must never survive as
# observable surface forms once Layer 6 has linked them to a parameter.
BARE_NUMERIC_RE = re.compile(
    r"^[<>]?\d+(?:\.\d+)?(?:\s*[%/\-\^0-9a-z]+)?(?:\s*Hb/g)?$",
    re.IGNORECASE,
)

# Trailing punctuation the LLM frequently leaves on extracted spans.
_TRAILING_PUNCT = ".,;:()[]{}"


def strip_value_unit_tail(text: str) -> str:
    """Strip a trailing value+unit (and optional ref range) from a surface form.

    Returns the cleaned text. If the regex strips everything (i.e. the entire
    input was a value with no parameter name), the original input is returned
    so downstream code can still reason about it; the caller should filter
    bare numerics separately via ``is_bare_numeric``.

    Order matters here: trailing punctuation is stripped only AFTER the regex
    runs, because the regex's optional ``\\(...\\)`` clause needs the closing
    paren of a reference range to match successfully.
    """
    if not text:
        return text
    candidate = re.sub(r"\s+", " ", text).strip()
    if not candidate:
        return ""
    stripped = VALUE_UNIT_TAIL_RE.sub("", candidate).strip().strip(_TRAILING_PUNCT)
    if stripped:
        return stripped
    return candidate.strip(_TRAILING_PUNCT)


def is_bare_numeric(text: str) -> bool:
    """True when the text is just a number / range / percentage with no name."""
    candidate = text.strip().casefold()
    if not candidate:
        return False
    return BARE_NUMERIC_RE.fullmatch(candidate) is not None


def clean_observable_surface_text(text: str) -> str:
    """Canonical observable surface-form cleanup applied by Layer 4b.

    Combines whitespace collapse, trailing-punctuation trim, and value/unit
    tail strip. Returns an empty string when only a numeric token would
    remain, so the caller can drop the entity in Layer 4b.
    """
    if not text:
        return ""
    cleaned = strip_value_unit_tail(text)
    if not cleaned:
        return ""
    if is_bare_numeric(cleaned):
        return ""
    return cleaned
