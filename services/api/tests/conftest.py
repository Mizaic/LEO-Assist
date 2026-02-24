"""Pytest configuration and fixtures for API tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure app is importable when running from project root or services/api
API_ROOT = Path(__file__).resolve().parent.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
