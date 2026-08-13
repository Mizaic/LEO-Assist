"""Tests for patient document inline file streaming."""

from __future__ import annotations

import pathlib

import pytest

from libs.patient_documents.file_stream import resolve_document_file_target

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTER = (
    ROOT
    / "services"
    / "analytics_api"
    / "app"
    / "routers"
    / "patient_document_files.py"
)
QUERIES = (
    ROOT / "services" / "analytics_api" / "app" / "routers" / "patients_epr_queries.py"
)


def test_resolve_document_file_target_prefers_original_url():
    result = resolve_document_file_target(
        original_url="https://acct.blob.core.windows.net/c/a.pdf",
        markdown_url="https://acct.blob.core.windows.net/c/a.md",
        content_type="application/pdf",
        title="Clinical Information.pdf",
    )
    assert result is not None
    url, media_type, filename = result
    assert url.startswith("https://acct.blob.core.windows.net/c/a.pdf")
    assert media_type == "application/pdf"
    assert filename == "Clinical_Information.pdf"


def test_resolve_document_file_target_returns_none_without_urls():
    assert (
        resolve_document_file_target(
            original_url="",
            markdown_url=None,
            content_type=None,
            title="Clinical Information.pdf",
        )
        is None
    )


def test_document_file_router_and_queries_exist():
    router_src = ROUTER.read_text(encoding="utf-8")
    queries_src = QUERIES.read_text(encoding="utf-8")
    assert "/documents/{document_id}/file" in router_src
    assert "/documents/{document_id}/preview" in router_src
    assert "StreamingResponse" in router_src
    assert "build_chunk_fallback_preview" in router_src
    assert "GET_DOCUMENT_FILE_ADMIN" in queries_src
    assert "GET_DOCUMENT_FILE_SCOPED" in queries_src
    assert "full_text" in queries_src
    assert "chunk_count" in queries_src


@pytest.mark.parametrize(
    ("title", "url", "expected_suffix"),
    [
        ("Report", "https://x/y", ".pdf"),
        ("notes", "https://x/y", ".md"),
    ],
)
def test_resolve_document_file_target_infers_extension(
    title: str,
    url: str,
    expected_suffix: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "libs.patient_documents.file_stream.sign_patient_document_url",
        lambda value: value,
    )
    media_type = "application/pdf" if expected_suffix == ".pdf" else "text/markdown"
    result = resolve_document_file_target(
        original_url=url,
        markdown_url=None,
        content_type=media_type,
        title=title,
    )
    assert result is not None
    _, _, filename = result
    assert filename.endswith(expected_suffix)
