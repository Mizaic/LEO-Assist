"""Unit tests for scripts/ci/detect_changed_services.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "detect_changed_services.py"


def _load():
    spec = importlib.util.spec_from_file_location("detect_changed_services", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def detect_mod():
    return _load()


def test_force_all_builds_everything(detect_mod):
    backend, build_ui, build_all = detect_mod.detect([], force_all=True)
    assert build_all is True
    assert build_ui is True
    assert {row["service"] for row in backend} == {
        "core-api",
        "terminology-api",
        "fhir-api",
        "analytics-api",
        "pipeline-worker",
        "model-inference",
        "training-worker",
        "research-worker",
    }


def test_ui_only_change(detect_mod):
    backend, build_ui, build_all = detect_mod.detect(
        ["services/ui/src/app/page.tsx"],
        force_all=False,
    )
    assert build_all is False
    assert build_ui is True
    assert backend == []


def test_libs_blast_radius(detect_mod):
    backend, build_ui, build_all = detect_mod.detect(
        ["libs/pipeline/post_processing.py"],
        force_all=False,
    )
    assert build_all is True
    assert build_ui is True
    assert len(backend) == 8


def test_terminology_rebuilds_consumers(detect_mod):
    backend, build_ui, build_all = detect_mod.detect(
        ["services/terminology_api/app/main.py"],
        force_all=False,
    )
    assert build_all is False
    assert build_ui is False
    names = {row["service"] for row in backend}
    assert names == {"core-api", "terminology-api", "pipeline-worker"}


def test_docs_only_builds_nothing(detect_mod):
    backend, build_ui, build_all = detect_mod.detect(
        ["docs/VALIDATION-LAB.md", "README.md"],
        force_all=False,
    )
    assert build_all is False
    assert build_ui is False
    assert backend == []


def test_single_dockerfile_is_scoped(detect_mod):
    backend, build_ui, build_all = detect_mod.detect(
        ["infra/dockerfiles/Dockerfile.training-worker"],
        force_all=False,
    )
    assert build_all is False
    assert build_ui is False
    assert [row["service"] for row in backend] == ["training-worker"]
