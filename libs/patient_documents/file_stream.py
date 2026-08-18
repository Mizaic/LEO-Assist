"""Stream patient document files through the analytics API.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Browsers cannot embed Azure blob URLs in iframes when the app CSP only
allows frame-src 'self'. This module resolves a signed blob URL and
streams bytes back on a same-origin path.
"""

from __future__ import annotations

import re
from typing import AsyncIterator, Optional

import httpx

from libs.patient_documents.blob_url_signer import sign_patient_document_url

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def resolve_document_file_target(
    *,
    original_url: str | None,
    markdown_url: str | None,
    content_type: str | None,
    title: str | None,
) -> Optional[tuple[str, str, str]]:
    """Return signed url, media type, and safe filename for inline viewing."""
    raw_url = (original_url or "").strip() or (markdown_url or "").strip()
    if not raw_url:
        return None

    signed = sign_patient_document_url(raw_url) or raw_url
    media_type = _infer_media_type(content_type, raw_url, title)
    filename = _safe_filename(title, raw_url, media_type)
    return signed, media_type, filename


def _infer_media_type(
    content_type: str | None,
    url: str,
    title: str | None,
) -> str:
    ct = (content_type or "").strip().lower()
    if ct:
        return ct

    candidates = [(title or "").lower(), url.lower()]
    for value in candidates:
        if value.endswith(".pdf"):
            return "application/pdf"
        if value.endswith(".docx"):
            return (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            )
        if value.endswith(".doc"):
            return "application/msword"
        if value.endswith(".md") or value.endswith(".markdown"):
            return "text/markdown"
        if value.endswith(".html") or value.endswith(".htm"):
            return "text/html"
    return "application/octet-stream"


def _safe_filename(title: str | None, url: str, media_type: str) -> str:
    base = (title or "").strip() or url.rsplit("/", 1)[-1].split("?", 1)[0]
    cleaned = _FILENAME_UNSAFE.sub("_", base).strip("._") or "document"
    if "." not in cleaned:
        if media_type == "application/pdf":
            cleaned = f"{cleaned}.pdf"
        elif media_type == "text/markdown":
            cleaned = f"{cleaned}.md"
    return cleaned[:180]


async def stream_remote_file(url: str) -> AsyncIterator[bytes]:
    """Fetch a remote file and yield response chunks."""
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk
