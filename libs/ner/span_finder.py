"""Helpers to find mention spans inside generated sentences.

Atlas trace:
  DO: DO-8EF2EC20
  DI: DI-2F963FC6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8EF2EC20")
"""

from __future__ import annotations

import re
import unicodedata

_READ_CODE_RE = r"\([A-Za-z0-9.]{2,12}\)"
_MEASUREMENT_START_RE = re.compile(r"(?<![A-Za-z0-9])(?:[<>]=?|[\u2264\u2265])?\s*\d")


def _normalise(text: str) -> str:
    """Normalise text for fuzzy span matching.

    Converts to NFKC unicode, collapses unicode dash/quote variants to ASCII
    equivalents, and squeezes runs of whitespace.  Does NOT lowercase so that
    offset re-mapping works correctly.
    """
    # NFKC: compatibility decomposition + canonical composition
    text = unicodedata.normalize("NFKC", text)
    # En-dash / em-dash / minus sign / figure dash -> hyphen
    text = re.sub(r"[\u2013\u2014\u2212\u2012]", "-", text)
    # Curly quotes -> straight
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    # Collapse whitespace runs
    text = re.sub(r"\s+", " ", text)
    return text


def _flexible_literal_pattern(text: str) -> str:
    """Escape text while allowing whitespace runs to vary."""

    parts = re.split(r"\s+", text.strip())
    return r"\s+".join(re.escape(part) for part in parts if part)


def _optional_read_code_pattern(form: str) -> re.Pattern[str] | None:
    """Build a lab pattern for text with an omitted embedded Read code."""

    if "(" in form or ")" in form:
        return None

    measurement = _MEASUREMENT_START_RE.search(form)
    if measurement is None:
        return None

    prefix = form[: measurement.start()].strip()
    suffix = form[measurement.start() :].strip()
    if not prefix or not suffix:
        return None

    return re.compile(
        rf"{_flexible_literal_pattern(prefix)}\s+(?:{_READ_CODE_RE}\s+)?"
        rf"{_flexible_literal_pattern(suffix)}",
        re.IGNORECASE,
    )


def _find_with_optional_read_code(sentence: str, form: str) -> tuple[int, int] | None:
    """Find lab surfaces whose stored text omitted the embedded Read code.

    Historical gold labels often store a cleaned observable surface such as
    ``Urine creatinine level 5.5 mmol/L`` while the source sentence contains
    ``Urine creatinine level (XE2qO) 5.5 mmol/L``. The training span must be
    contiguous in the sentence, so the repaired span should include the code.
    """

    pattern = _optional_read_code_pattern(form)
    if pattern is None:
        return None

    match = pattern.search(sentence)
    if match:
        return match.start(), match.end()
    return None


def find_span_candidates(sentence: str, surface_form: str) -> list[tuple[int, int]]:
    """Return candidate spans for ambiguity checks.

    This intentionally covers the deterministic match modes used for repair:
    exact case-insensitive surface matches and cleaned lab observables with an
    omitted embedded Read code.
    """

    if not sentence or not surface_form:
        return []

    exact = re.compile(re.escape(surface_form), re.IGNORECASE)
    candidates = [(m.start(), m.end()) for m in exact.finditer(sentence)]
    code_pattern = _optional_read_code_pattern(surface_form)
    if code_pattern is None:
        return candidates

    for match in code_pattern.finditer(sentence):
        candidate = (match.start(), match.end())
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def find_span(
    sentence: str,
    surface_form: str,
    *alternate_forms: str,
) -> tuple[int, int] | None:
    """Find the first case-insensitive mention span for ``surface_form``.

    Tries each form in order:
    1. Exact match (case-insensitive).
    2. Normalised match -- collapses unicode dashes/quotes/whitespace before
       comparing.  This repairs spans broken by em-dash vs hyphen mismatches
       or whitespace changes after the record was edited.
    3. Lab/observation match where the stored cleaned surface omitted an
       embedded Read/CTV3 code from the source sentence.

    Returns character offsets into the ORIGINAL ``sentence`` string.
    """
    for form in (surface_form, *alternate_forms):
        if not form or not sentence:
            continue
        # Pass 1: exact
        pattern = re.compile(re.escape(form), re.IGNORECASE)
        m = pattern.search(sentence)
        if m:
            return m.start(), m.end()

        # Pass 2: normalised
        norm_sentence = _normalise(sentence)
        norm_form = _normalise(form)
        if not norm_form:
            continue
        norm_pattern = re.compile(re.escape(norm_form), re.IGNORECASE)
        nm = norm_pattern.search(norm_sentence)
        if nm:
            # Map normalised offsets back to original string.
            # Because _normalise may collapse whitespace, we find the first
            # occurrence of the matched substring in the original text.
            matched_text = norm_sentence[nm.start() : nm.end()]
            orig_m = re.search(re.escape(matched_text), sentence, re.IGNORECASE)
            if orig_m:
                return orig_m.start(), orig_m.end()
            # Fallback: use normalised offsets directly (close enough for span
            # realignment -- only affects records with whitespace collapsing)
            return nm.start(), nm.end()

        # Pass 3: cleaned lab observable text, source contains a Read code.
        code_match = _find_with_optional_read_code(sentence, form)
        if code_match:
            return code_match
    return None
