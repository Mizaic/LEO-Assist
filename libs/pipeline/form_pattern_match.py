"""Markdown-table-aware pattern matching for taught form schemas.

Referral letters reach LEO as markdown pipe tables. Section headings sit
inside table cells, and every heading is followed by a separator row such
as ``| --- |``. Taught start patterns come from three places: the LLM
detector, the deterministic splitter, and a clinician typing a label into
the teach dialog. Only the first reliably produces a valid regular
expression, so matching must never raise.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import re

_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_INLINE_FLAGS = re.compile(r"\(\?[aiLmsux]+\)")
_CLASS_ESCAPES = re.compile(r"\\[sdwbSDWBAZ]")
_WORD = re.compile(r"[A-Za-z0-9]+")


def is_table_separator(line: str) -> bool:
    """Return True when *line* is a markdown table separator row.

    Separator rows carry no content. They must never be treated as a
    section heading or as clinical text.
    """
    stripped = line.strip()
    if not stripped or "-" not in stripped:
        return False
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    populated = [c for c in cells if c]
    if not populated:
        return False
    return all(_SEPARATOR_CELL.match(c) for c in populated)


def cell_texts(line: str) -> list[str]:
    """Return the non-empty cell contents of a markdown table row.

    A line with no pipe characters is returned as a single cell.
    """
    stripped = line.strip()
    if "|" not in stripped:
        return [stripped] if stripped else []
    return [c.strip() for c in stripped.strip("|").split("|") if c.strip()]


def _literal_fallback(pattern: str) -> str:
    """Build a tolerant pattern from the word tokens of an unusable regex.

    Words are joined with ``\\s+`` so a pasted label still matches its own
    row when the raw text contains different spacing.
    """
    cleaned = _INLINE_FLAGS.sub(" ", pattern)
    cleaned = _CLASS_ESCAPES.sub(" ", cleaned)
    tokens = _WORD.findall(cleaned)
    if not tokens:
        return ""
    return r"\s*\W*\s*".join(re.escape(t) for t in tokens)


def safe_search(pattern: str, text: str) -> re.Match[str] | None:
    """Search *text* for *pattern*, never raising on a bad pattern.

    Falls back to a whitespace-tolerant literal match built from the
    pattern's word tokens when the pattern will not compile.
    """
    if not pattern or not text:
        return None
    try:
        return re.search(pattern, text, re.IGNORECASE)
    except re.error:
        pass
    try:
        return re.search(re.escape(pattern), text, re.IGNORECASE)
    except re.error:
        pass
    fallback = _literal_fallback(pattern)
    if not fallback:
        return None
    try:
        return re.search(fallback, text, re.IGNORECASE)
    except re.error:
        return None


def section_matches(pattern: str, line: str) -> bool:
    """Return True when *line* starts the section described by *pattern*."""
    if not pattern or is_table_separator(line):
        return False
    return safe_search(pattern, line) is not None
