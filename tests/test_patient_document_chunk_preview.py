"""Tests for chunk text fallback preview."""

from __future__ import annotations

from libs.patient_documents.chunk_preview import (
    build_chunk_fallback_preview,
    chunk_text_to_preview_html,
)


def test_chunk_text_to_preview_html_wraps_paragraphs():
    html = chunk_text_to_preview_html("Line one\n\nLine two")
    assert "<p>Line one</p>" in html
    assert "<p>Line two</p>" in html


def test_build_chunk_fallback_preview_adds_warning():
    html, warnings = build_chunk_fallback_preview("Referral body")
    assert "Referral body" in html
    assert warnings
    assert "AI-processed text" in warnings[0]


def test_build_chunk_fallback_preview_empty_text():
    html, warnings = build_chunk_fallback_preview("   ")
    assert html == ""
    assert warnings == []
