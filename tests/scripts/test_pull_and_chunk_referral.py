"""Tests for the local referral pull-and-chunk validation helpers.

Atlas trace:
  VT: VT-3FE08AC5
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-3FE08AC5")
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libs.chunking.converter_client import (
    ConverterError,
    converter_path,
    needs_conversion,
    parse_markdown_response,
)
from libs.chunking.validation_bundle import load_bundle, write_bundle
from scripts.pull_and_chunk_referral import list_documents, resolve_referral_ids


def test_converter_path_uses_extract_for_pdf_and_images() -> None:
    assert converter_path("application/pdf") == "/extract"
    assert converter_path("image/png") == "/extract"
    assert converter_path("image/jpeg") == "/extract"


def test_converter_path_uses_extract_for_word() -> None:
    # /convert returns PDF or HTML, not markdown. /extract is the
    # markdown path for Word as well as PDF and images.
    assert (
        converter_path(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        == "/extract"
    )
    assert converter_path("application/msword") == "/extract"


def test_needs_conversion_skips_already_markdown() -> None:
    assert needs_conversion("text/markdown") is False
    assert needs_conversion("text/plain") is False
    assert needs_conversion("application/pdf") is True


def test_parse_markdown_response_returns_markdown() -> None:
    text = parse_markdown_response({"success": True, "markdown": "# Labs\n\nHb 120"})
    assert "Hb 120" in text


def test_parse_markdown_response_rejects_empty() -> None:
    with pytest.raises(ConverterError):
        parse_markdown_response({"success": True, "markdown": "   "})


def test_parse_markdown_response_rejects_failure() -> None:
    with pytest.raises(ConverterError):
        parse_markdown_response(
            {"success": False, "message": "unsupported", "markdown": ""}
        )


def test_write_and_load_bundle_round_trip(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "document_reference_id": "dr-1",
            "ordinal": 1,
            "sha256": "abc",
            "text": "Hb 120",
            "char_start": 0,
            "char_end": 6,
        }
    ]
    manifest = {
        "patient_id": "p1",
        "referral_id": "r1",
        "doc_count": 1,
        "chunk_count": 1,
    }
    dest = write_bundle(
        tmp_path,
        referral_id="r1",
        manifest=manifest,
        chunks=chunks,
        chunks_deid=[{"text": "Hb 120"}],
    )
    assert (dest / "chunks.json").is_file()
    assert (dest / "chunks_deid.json").is_file()
    assert (dest / "manifest.json").is_file()

    loaded = load_bundle(dest)
    assert loaded.manifest["referral_id"] == "r1"
    assert loaded.chunks[0]["chunk_id"] == "c1"
    assert loaded.chunks_deid[0]["text"] == "Hb 120"


def test_write_bundle_omits_deid_when_absent(tmp_path: Path) -> None:
    dest = write_bundle(
        tmp_path,
        referral_id="r2",
        manifest={"referral_id": "r2"},
        chunks=[],
    )
    assert not (dest / "chunks_deid.json").exists()
    raw = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert raw["referral_id"] == "r2"


def test_resolve_referral_ids_from_patient() -> None:
    client = MagicMock()
    client.run.return_value = [{"referral_id": "0001"}]
    assert resolve_referral_ids(client, patient_id="p1") == ["0001"]


def test_resolve_referral_ids_requires_one_selector() -> None:
    client = MagicMock()
    with pytest.raises(ValueError):
        resolve_referral_ids(client)


def test_list_documents_returns_doc_rows() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "doc_id": "dr-1",
            "url": "https://example.blob.core.windows.net/c/a.pdf",
            "content_type": "application/pdf",
            "title": "Clinical information",
        }
    ]
    rows = list_documents(client, "0001")
    assert rows[0]["doc_id"] == "dr-1"
    assert rows[0]["content_type"] == "application/pdf"
