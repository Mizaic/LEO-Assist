"""Helpers to find mention spans inside generated sentences."""

from __future__ import annotations

import re


def find_span(
    sentence: str,
    surface_form: str,
    *alternate_forms: str,
) -> tuple[int, int] | None:
    """Find the first case-insensitive mention span for ``surface_form``.

    If ``surface_form`` is not found, each ``alternate_forms`` entry is tried
    in order.  This lets callers pass the clean preferred term as a fallback so
    that sentences written with the full clinical term (rather than the stored
    abbreviation) still produce a valid span.
    """
    for form in (surface_form, *alternate_forms):
        if not form or not sentence:
            continue
        pattern = re.compile(re.escape(form), re.IGNORECASE)
        match = pattern.search(sentence)
        if match:
            return match.start(), match.end()
    return None
