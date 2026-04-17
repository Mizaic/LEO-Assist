"""Inspection tests for the spancat suggester capacity (VT-LEO-AI-156).

Verifies that services/training_worker/app/config/base.cfg sets the
spancat ngram_range_suggester max_size to a value large enough that the
spancat model can natively propose, score, and learn the long observable
spans seen on UK primary-care lab lines (typically 18-22 tokens).

These are pure file-inspection tests; no spaCy / training import is
required, so they run in well under a second and do not depend on the
training_worker package being importable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "training_worker"
    / "app"
    / "config"
    / "base.cfg"
)


def _read_suggester_int(key: str) -> int:
    """Return the integer value of [components.spancat.suggester].<key>.

    Parses the section manually so the test does not depend on configparser
    quirks with spaCy's TOML-ish syntax (string quoting, list literals).
    """
    if not CONFIG_PATH.exists():
        pytest.fail(f"Training config not found at {CONFIG_PATH}")

    text = CONFIG_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"\[components\.spancat\.suggester\]\s*\n(.*?)(?=\n\[|\Z)",
        text,
        re.DOTALL,
    )
    if section_match is None:
        pytest.fail("Section [components.spancat.suggester] missing from base.cfg")

    section = section_match.group(1)
    value_match = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*(\d+)\s*$",
        section,
        re.MULTILINE,
    )
    if value_match is None:
        pytest.fail(f"Key {key!r} missing from spancat.suggester section")
    return int(value_match.group(1))


def test_spancat_suggester_max_size_is_at_least_24() -> None:
    """max_size must be >= 24 so 18-22 token observable spans can be suggested."""
    assert _read_suggester_int("max_size") >= 24


def test_spancat_suggester_min_size_is_one() -> None:
    """Single-token spans (acronyms, codes) must still be suggested."""
    assert _read_suggester_int("min_size") == 1


def test_spancat_suggester_max_size_is_capped_at_32() -> None:
    """Per DI-LEO-AI-158, max_size > 32 requires a separate performance review."""
    assert _read_suggester_int("max_size") <= 32
