"""Fallback document preview from stored pipeline chunks.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import html as html_module
import re

_CHUNK_FALLBACK_WARNING = (
    "Showing AI-processed text because the original file could not be loaded."
)


def chunk_text_to_preview_html(text: str) -> str:
    """Render stored chunk text as simple HTML paragraphs."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()
    ]
    blocks: list[str] = []
    for paragraph in paragraphs:
        escaped = html_module.escape(paragraph).replace("\n", "<br/>")
        blocks.append(f"<p>{escaped}</p>")
    return "".join(blocks)


def build_chunk_fallback_preview(full_text: str) -> tuple[str, list[str]]:
    """Build preview HTML and warnings from concatenated chunk text."""
    html = chunk_text_to_preview_html(full_text)
    if not html.strip():
        return "", []
    return html, [_CHUNK_FALLBACK_WARNING]
