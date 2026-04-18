"""Unit VT for the timeline loader (VT-LEO-AI-500)."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.analysis_worker.app.episode_engine.timeline_loader import (
    _normalise,
    _trunk_line,
    load_timeline,
)


def test_normalise_collapses_whitespace_and_newlines():
    """VT-500-TC-001: newlines/tabs collapse, multi-spaces collapse, ' / ' join."""

    raw = "Line one\n  Line two\nLine three  with   spaces"
    out = _normalise(raw)
    assert out == "Line one / Line two / Line three with spaces"


def test_normalise_handles_empty():
    """VT-500-TC-002: empty/None input -> empty string."""

    assert _normalise(None) == ""
    assert _normalise("") == ""


def test_trunk_line_caps_snippet_length_and_short_id():
    """VT-500-TC-003: trunk lines cap snippet to 240 chars with short id prefix."""

    long_text = "x" * 1000
    line = _trunk_line("0123456789abcdef", long_text)
    assert line.startswith("  [01234567] ")
    body = line[len("  [01234567] "):]
    assert len(body) == 240


def test_load_timeline_groups_records_by_date():
    """VT-500-TC-004: encounters on the same date are grouped under one header."""

    client = MagicMock()
    client.run.return_value = [
        {
            "encounter_id": "enc-aaaaaaaa",
            "date": "2025-03-26",
            "text": "Fast track referral.",
            "flags": None,
            "coding_status": "complete",
        },
        {
            "encounter_id": "enc-bbbbbbbb",
            "date": "2025-03-26",
            "text": "PRISM 2WW questionnaire.",
            "flags": None,
            "coding_status": "complete",
        },
        {
            "encounter_id": "enc-cccccccc",
            "date": "2025-04-28",
            "text": "Seen in clinic.",
            "flags": None,
            "coding_status": "complete",
        },
    ]

    trunk_text, encounter_index, count = load_timeline("p-1", client=client)

    assert count == 3
    assert set(encounter_index.keys()) == {"enc-aaaaaaaa", "enc-bbbbbbbb", "enc-cccccccc"}
    assert "== 2025-03-26 (2 records) ==" in trunk_text
    assert "== 2025-04-28 (1 record) ==" in trunk_text
    assert "[enc-aaaa]" in trunk_text
    assert "[enc-bbbb]" in trunk_text
    assert "[enc-cccc]" in trunk_text


def test_load_timeline_skips_rows_without_encounter_id():
    """VT-500-TC-005: rows missing encounter_id are silently skipped."""

    client = MagicMock()
    client.run.return_value = [
        {"encounter_id": None, "date": "2025-03-26", "text": "broken row"},
        {
            "encounter_id": "enc-good",
            "date": "2025-03-26",
            "text": "good row",
        },
    ]
    trunk, idx, count = load_timeline("p-1", client=client)
    assert count == 1
    assert "enc-good" in idx
    assert "broken row" not in trunk


def test_load_timeline_no_encounters_returns_empty():
    """VT-500-TC-006: no encounters -> ('', {}, 0)."""

    client = MagicMock()
    client.run.return_value = []
    trunk, idx, count = load_timeline("p-1", client=client)
    assert (trunk, idx, count) == ("", {}, 0)


def test_load_timeline_full_snippet_present_in_index():
    """VT-500-TC-007: each encounter_index row carries a full_snippet field."""

    client = MagicMock()
    client.run.return_value = [
        {
            "encounter_id": "enc-1",
            "date": "2025-03-26",
            "text": "Some clinical note that should appear in full_snippet.",
            "flags": None,
            "coding_status": None,
        }
    ]
    _, idx, _ = load_timeline("p-1", client=client)
    record = idx["enc-1"]
    assert "full_snippet" in record
    assert "clinical note" in record["full_snippet"]
