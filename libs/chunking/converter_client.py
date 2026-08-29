"""Client helpers for the local HCCP doc converter at :8012.

``POST /convert`` returns PDF or HTML. ``POST /extract`` returns
markdown for Word, PDF, HTML, and images. Validation always uses
``/extract``.
"""

from __future__ import annotations

from typing import Any

_MARKDOWN_TYPES = frozenset({"text/markdown", "text/plain"})


class ConverterError(RuntimeError):
    """Raised when the converter does not return usable markdown."""


def converter_path(content_type: str) -> str:
    """Return the converter path that produces markdown.

    Word, PDF, and images all go to ``/extract``. ``/convert`` is the
    wrong path for this job because it returns PDF or HTML.
    """
    del content_type
    return "/extract"


def needs_conversion(content_type: str) -> bool:
    """Return True when the binary still needs markdown conversion."""
    return (content_type or "").split(";", 1)[0].strip().lower() not in _MARKDOWN_TYPES


def parse_markdown_response(payload: dict[str, Any]) -> str:
    """Pull markdown from an extract JSON body."""
    if payload.get("success") is False:
        message = str(payload.get("message") or "converter rejected the file")
        raise ConverterError(message)
    markdown = str(payload.get("markdown") or "").strip()
    if not markdown:
        raise ConverterError("converter returned empty markdown")
    return markdown
