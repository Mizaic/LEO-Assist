"""Inspection tests for the spancat suggester capacity (VT-LEO-AI-156).

Verifies that services/training_worker/app/config/base.cfg sets the
clinical spancat suggester sizes large enough that the spancat model can
natively propose, score, and learn the nested observable_entity and finding
spans seen on UK primary-care lab lines.

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


def _read_suggester_sizes() -> list[int]:
    """Return [components.spancat.suggester].sizes from the training config.

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
        r"^\s*sizes\s*=\s*\[(.*?)\]\s*$",
        section,
        re.MULTILINE,
    )
    if value_match is None:
        pytest.fail("Key 'sizes' missing from spancat.suggester section")
    return [int(raw.strip()) for raw in value_match.group(1).split(",")]


def test_spancat_suggester_covers_completed_gold_lab_lengths() -> None:
    """The model must be able to suggest known positive lab span lengths."""
    sizes = set(_read_suggester_sizes())
    assert set(range(1, 11)) <= sizes
    assert {15, 20, 21, 22, 24} <= sizes


def test_spancat_suggester_avoids_full_middle_band() -> None:
    """Full 1..24 coverage needs separate pruning before reintroduction."""
    sizes = set(_read_suggester_sizes())
    assert not ({11, 12, 13, 14, 16, 17, 18, 19} & sizes)


def test_spancat_suggester_min_size_is_one() -> None:
    """Single-token spans (acronyms, codes) must still be suggested."""
    assert min(_read_suggester_sizes()) == 1


def test_spancat_suggester_max_size_is_capped_at_32() -> None:
    """Per DI-LEO-AI-158, sizes > 32 require a separate performance review."""
    assert max(_read_suggester_sizes()) <= 32
