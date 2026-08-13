"""Tests for server-side Word document preview."""

from __future__ import annotations

import io
import pathlib
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from libs.patient_documents.docx_preview import (
    build_word_preview_html,
    convert_docx_bytes_to_html,
    is_legacy_doc_file,
    is_word_document,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTER = (
    ROOT
    / "services"
    / "analytics_api"
    / "app"
    / "routers"
    / "patient_document_files.py"
)


def _minimal_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Referral preview text</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    return buffer.getvalue()


def test_is_word_document_detects_docx_title():
    assert is_word_document(None, "Clinical Information.docx", "https://x/y")


def test_is_word_document_detects_azure_blob_suffix():
    assert is_word_document(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "BR16 updated 62.docx",
        "https://storagehdtnonprod.blob.core.windows.net/c/uuid.vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def test_is_legacy_doc_file_detects_old_format():
    assert is_legacy_doc_file("Report.doc", "https://x/y.doc")
    assert not is_legacy_doc_file("Report.docx", "https://x/y.docx")


def test_convert_docx_bytes_to_html():
    mammoth = pytest.importorskip("mammoth")
    del mammoth
    html, warnings = convert_docx_bytes_to_html(_minimal_docx_bytes())
    assert "Referral preview text" in html
    assert isinstance(warnings, list)


@pytest.mark.asyncio
async def test_build_word_preview_html_rejects_legacy_doc():
    with pytest.raises(ValueError, match="Legacy .doc"):
        await build_word_preview_html(
            original_url="https://acct.blob.core.windows.net/c/a.doc",
            markdown_url=None,
            content_type="application/msword",
            title="Report.doc",
        )


@pytest.mark.asyncio
async def test_build_word_preview_html_fetches_and_converts_docx():
    mammoth = pytest.importorskip("mammoth")
    del mammoth
    docx = _minimal_docx_bytes()
    with patch(
        "libs.patient_documents.docx_preview.fetch_remote_file_bytes",
        new=AsyncMock(return_value=docx),
    ):
        html, _warnings = await build_word_preview_html(
            original_url="https://acct.blob.core.windows.net/c/a.docx",
            markdown_url=None,
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            title="Clinical Information.docx",
        )
    assert "Referral preview text" in html


def test_preview_route_is_registered():
    src = ROUTER.read_text(encoding="utf-8")
    assert "/documents/{document_id}/preview" in src
    assert "build_word_preview_html" in src
    assert "DocumentPreviewResponse" in src
