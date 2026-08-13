"""Server-side Word document preview for the Care document viewer."""

from __future__ import annotations

import io
import re
from typing import Optional

import httpx

from libs.patient_documents.file_stream import resolve_document_file_target

_DOCX_SUFFIX = ".docx"
_LEGACY_DOC_SUFFIX = ".doc"


def is_word_document(
    content_type: str | None,
    title: str | None,
    url: str,
) -> bool:
    ct = (content_type or "").lower()
    if "word" in ct or "docx" in ct or "msword" in ct:
        return True
    candidates = [(title or "").lower(), url.lower()]
    for name in candidates:
        if name.endswith(_DOCX_SUFFIX):
            return True
        if "wordprocessingml.document" in name:
            return True
        if name.endswith(_LEGACY_DOC_SUFFIX) and not name.endswith(_DOCX_SUFFIX):
            return True
    return False


def is_legacy_doc_file(title: str | None, url: str) -> bool:
    candidates = [(title or "").lower(), url.lower()]
    for name in candidates:
        if name.endswith(_LEGACY_DOC_SUFFIX) and not name.endswith(_DOCX_SUFFIX):
            return True
    return False


async def fetch_remote_file_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _format_mammoth_warning(message: object) -> str:
    text = getattr(message, "message", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    raw = str(message).strip()
    if raw.startswith("Message(") and "message=" in raw:
        match = re.search(r"message='([^']*)'", raw)
        if match:
            return match.group(1).strip()
    return raw


def convert_docx_bytes_to_html(docx_bytes: bytes) -> tuple[str, list[str]]:
    import mammoth

    result = mammoth.convert_to_html(io.BytesIO(docx_bytes))
    warnings = [
        warning
        for warning in (_format_mammoth_warning(message) for message in result.messages)
        if warning
    ]
    return result.value or "", warnings


async def build_word_preview_html(
    *,
    original_url: str | None,
    markdown_url: str | None,
    content_type: str | None,
    title: str | None,
) -> tuple[str, list[str]]:
    target = resolve_document_file_target(
        original_url=original_url,
        markdown_url=markdown_url,
        content_type=content_type,
        title=title,
    )
    if not target:
        raise ValueError("Document file URL not available.")

    signed_url, media_type, filename = target
    if not is_word_document(content_type, title or filename, signed_url):
        raise ValueError("Preview is only available for Word documents.")
    if is_legacy_doc_file(title or filename, signed_url):
        raise ValueError(
            "Legacy .doc files are not supported. Use .docx or Open in new tab."
        )

    docx_bytes = await fetch_remote_file_bytes(signed_url)
    return convert_docx_bytes_to_html(docx_bytes)
