"""Floors for the UI container findings on the Aikido image named ui."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = ROOT / "package-lock.json"
DOCKERFILE = ROOT / "infra" / "dockerfiles" / "Dockerfile.ui"
UI_MANIFEST = ROOT / "services" / "ui" / "package.json"

NEXT_FLOOR = (16, 4, 1)
SHARP_FLOOR = (0, 35, 5)
NODE_IMAGE = "node:22.23.4-bookworm-slim"
RUNTIME_IMAGE = "gcr.io/distroless/nodejs22-debian13:nonroot"


def _version_tuple(version: str) -> tuple[int, ...]:
    core = version.split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


def _lock_version(package_path: str) -> str:
    lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    return lock["packages"][package_path]["version"]


def test_locked_next_meets_patched_floor() -> None:
    """Next.js in the image must be at least 16.4.1."""
    assert _version_tuple(_lock_version("node_modules/next")) >= NEXT_FLOOR


def test_locked_sharp_meets_patched_floor() -> None:
    """sharp pulled in by Next.js must be at least 0.35.5."""
    assert _version_tuple(_lock_version("node_modules/sharp")) >= SHARP_FLOOR


def test_ui_manifest_requests_patched_next() -> None:
    """The UI manifest must ask for a Next.js release on the patched line."""
    manifest = json.loads(UI_MANIFEST.read_text(encoding="utf-8"))
    requested = manifest["dependencies"]["next"].lstrip("^~")
    assert _version_tuple(requested) >= NEXT_FLOOR


def test_ui_dockerfile_pins_patched_base_images() -> None:
    """Build and runtime bases must be the patched Node 22 images."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert f"ARG BASE_IMAGE_NODE={NODE_IMAGE}" in text
    assert f"ARG BASE_IMAGE_RUNTIME={RUNTIME_IMAGE}" in text
