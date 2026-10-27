"""Floors for critical Aikido dependency findings that have a small fix."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = ROOT / "package-lock.json"
UI_MANIFEST = ROOT / "services" / "ui" / "package.json"
ANALYTICS_REQUIREMENTS = ROOT / "services" / "analytics_api" / "requirements.txt"

DOMPURIFY_FLOOR = (3, 4, 17)
UNDICI_FLOOR = (7, 29, 1)
AUTH_CORE_FLOOR = (0, 41, 3)
NEXT_AUTH_BETA_FLOOR = 32
MAMMOTH_FLOOR = (1, 11, 0)


def _numeric_version(version: str) -> tuple[int, ...]:
    core = version.split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


def _beta_number(version: str) -> int:
    match = re.search(r"-beta\.(\d+)$", version)
    if match is None:
        raise AssertionError(f"expected a beta version, got {version}")
    return int(match.group(1))


def _lock_version(package_path: str) -> str:
    lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    return lock["packages"][package_path]["version"]


def _ui_dependency(name: str) -> str:
    manifest = json.loads(UI_MANIFEST.read_text(encoding="utf-8"))
    return manifest["dependencies"][name].lstrip("^~")


def test_locked_dompurify_meets_critical_floor() -> None:
    """DOMPurify must be at least 3.4.17."""
    assert _numeric_version(_lock_version("node_modules/dompurify")) >= DOMPURIFY_FLOOR


def test_ui_requests_patched_dompurify() -> None:
    """The UI manifest must request the patched DOMPurify line."""
    assert _numeric_version(_ui_dependency("dompurify")) >= DOMPURIFY_FLOOR


def test_locked_undici_meets_critical_floor() -> None:
    """undici must be at least 7.29.1."""
    assert _numeric_version(_lock_version("node_modules/undici")) >= UNDICI_FLOOR


def test_ui_requests_patched_undici() -> None:
    """The UI manifest must request the patched undici line."""
    assert _numeric_version(_ui_dependency("undici")) >= UNDICI_FLOOR


def test_locked_next_auth_meets_critical_floor() -> None:
    """next-auth must be at least 5.0.0-beta.32."""
    version = _lock_version("node_modules/next-auth")
    assert _numeric_version(version) >= (5, 0, 0)
    assert _beta_number(version) >= NEXT_AUTH_BETA_FLOOR


def test_ui_requests_patched_next_auth() -> None:
    """The UI manifest must request the patched next-auth beta."""
    assert _beta_number(_ui_dependency("next-auth")) >= NEXT_AUTH_BETA_FLOOR


def test_locked_auth_core_meets_critical_floor() -> None:
    """@auth/core must be at least 0.41.3."""
    assert _numeric_version(_lock_version("node_modules/@auth/core")) >= AUTH_CORE_FLOOR


def test_analytics_mammoth_meets_critical_floor() -> None:
    """The analytics API must request mammoth 1.11.0 or newer."""
    text = ANALYTICS_REQUIREMENTS.read_text(encoding="utf-8")
    match = re.search(r"^mammoth>=([0-9.]+)", text, re.MULTILINE)
    assert match is not None
    assert _numeric_version(match.group(1)) >= MAMMOTH_FLOOR
