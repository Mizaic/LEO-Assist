"""Helpers to find mention spans inside generated sentences."""

from __future__ import annotations

import re


def find_span(sentence: str, surface_form: str) -> tuple[int, int] | None:
    """Find first case-insensitive mention span for ``surface_form``."""
    if not sentence or not surface_form:
        return None
    pattern = re.compile(re.escape(surface_form), re.IGNORECASE)
    match = pattern.search(sentence)
    if not match:
        return None
    return match.start(), match.end()
