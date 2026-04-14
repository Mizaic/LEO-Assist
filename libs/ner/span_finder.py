"""Helpers to find mention spans inside generated sentences."""

from __future__ import annotations

import re
import unicodedata


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
    return None
