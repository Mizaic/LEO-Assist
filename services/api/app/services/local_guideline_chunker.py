"""Heading-aware chunking for pasted local clinical guidelines.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?[A-Z][A-Za-z0-9 ,;:/()'-]{2,}$")


def chunk_by_heading(text: str) -> list[dict[str, str]]:
    """Split plain text into ordered heading sections without losing text."""
    chunks: list[dict[str, str]] = []
    title = "Introduction"
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _is_heading(line):
            _append_chunk(chunks, title, lines)
            title, lines = line, []
        elif line:
            lines.append(line)
    _append_chunk(chunks, title, lines)
    return chunks


def _is_heading(line: str) -> bool:
    """Return whether a non-empty line looks like a document heading."""
    return bool(_HEADING.match(line)) and not line.endswith(".")


def _append_chunk(chunks: list[dict[str, str]], title: str, lines: list[str]) -> None:
    """Append a non-empty heading section."""
    content = "\n".join(lines).strip()
    if content:
        chunks.append({"title": title, "text": content})
