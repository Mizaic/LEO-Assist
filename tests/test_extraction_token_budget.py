"""Extraction JSON output budget.

Atlas trace:
  DI: DI-7B978C0C
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-7B978C0C")
"""

from __future__ import annotations

import pytest

from libs.pipeline.extraction_token_budget import extraction_max_tokens


def test_floor_covers_a_typical_window() -> None:
    assert extraction_max_tokens(1) == 8192
    assert extraction_max_tokens(10) == 8192


def test_env_override_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTION_MAX_TOKENS", "16384")
    assert extraction_max_tokens(1) == 16384
    monkeypatch.setenv("EXTRACTION_MAX_TOKENS", "100")
    assert extraction_max_tokens(1) == 8192
    monkeypatch.setenv("EXTRACTION_MAX_TOKENS", "99999")
    assert extraction_max_tokens(1) == 16384
