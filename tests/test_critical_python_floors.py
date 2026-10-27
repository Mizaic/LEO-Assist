"""Floors for the remaining critical Python findings that can move safely."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FASTAPI_FLOOR = (0, 135, 0)
STARLETTE_FLOOR = (1, 0, 1)
H11_FLOOR = (0, 16, 0)
TORCH_FLOOR = (2, 6, 0)


def _numeric_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _floor(text: str, name: str) -> tuple[int, ...]:
    match = re.search(
        rf"^{name}(?:\[[^\]]+\])?>=([0-9]+(?:\.[0-9]+)*)",
        text,
        re.MULTILINE,
    )
    assert match is not None, name
    return _numeric_version(match.group(1))


def _requirement_files() -> list[Path]:
    files = [ROOT / "requirements.txt"]
    files.extend(sorted((ROOT / "services").glob("*/requirements.txt")))
    return files


def test_fastapi_and_starlette_meet_critical_floors() -> None:
    """Each API requirements file must allow Starlette 1.0.1."""
    checked = 0
    for path in _requirement_files():
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^fastapi(?:\[[^\]]+\])?>=", text, re.MULTILINE):
            continue
        checked += 1
        assert _floor(text, "fastapi") >= FASTAPI_FLOOR
        assert _floor(text, "starlette") >= STARLETTE_FLOOR
    assert checked >= 9


def test_h11_floor_is_pinned_where_http_clients_are_installed() -> None:
    """h11 must be at least 0.16.0 wherever an HTTP client is installed."""
    checked = 0
    for path in _requirement_files():
        text = path.read_text(encoding="utf-8")
        needs_h11 = "httpx" in text or path.parent.name == "terminology"
        if not needs_h11:
            continue
        checked += 1
        assert _floor(text, "h11") >= H11_FLOOR
    assert checked >= 2


def test_torch_floor_meets_critical_fix() -> None:
    """Torch floors below 2.6.0 must be raised. The Linux pin stays at 2.10."""
    inference = (
        ROOT / "services" / "model_inference" / "requirements.txt"
    ).read_text(encoding="utf-8")
    training = (
        ROOT / "services" / "training_worker" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert _floor(inference, "torch") >= TORCH_FLOOR
    assert "torch>=2.6.0; platform_system != \"Linux\"" in training
    assert "torch==2.10.0+cpu; platform_system == \"Linux\"" in training
