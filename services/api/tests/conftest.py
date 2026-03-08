"""Pytest configuration and fixtures for API tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure app is importable when running from project root or services/api
API_ROOT = Path(__file__).resolve().parent.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: marks tests that call live external APIs (requires NICE_API_KEY env var). "
        "Run with: pytest -m integration",
    )
