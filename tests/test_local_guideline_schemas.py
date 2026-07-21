"""Tests for local guideline request validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.schemas.local_guideline import LocalGuidelineMetadata


def test_local_guideline_short_code_accepts_uppercase_identifier() -> None:
    """A stable local identifier is accepted."""
    metadata = LocalGuidelineMetadata(short_code="SEL-MSK-01", title="MSK pathway")

    assert metadata.short_code == "SEL-MSK-01"


@pytest.mark.parametrize("short_code", ["ab", "sel_msk", "lower-case"])
def test_local_guideline_short_code_rejects_invalid_identifier(short_code: str) -> None:
    """Local identifiers require upper-case letters, numbers, and hyphens."""
    with pytest.raises(ValidationError):
        LocalGuidelineMetadata(short_code=short_code, title="MSK pathway")
