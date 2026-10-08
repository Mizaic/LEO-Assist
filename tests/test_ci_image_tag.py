"""Branch-suffixed image tags, and latest reserved for main."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TAG_SCRIPT = ROOT / "scripts" / "ci" / "image_tag.py"
MANIFEST_SCRIPT = ROOT / "scripts" / "ci" / "write_build_manifest.py"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci-build.yml"
CD_WORKFLOW = ROOT / ".github" / "workflows" / "cd-deploy.yml"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tag_mod():
    return _load(TAG_SCRIPT, "ci_image_tag")


def test_main_tag_keeps_sha_and_suffixes_main(tag_mod):
    sha = "a" * 40
    assert tag_mod.build_image_tag(sha, "main") == f"sha-{sha}-main"
    assert tag_mod.push_latest("main") is True


def test_feature_branch_suffix_replaces_slash_and_skips_latest(tag_mod):
    sha = "b" * 40
    assert tag_mod.build_image_tag(sha, "feature/widget") == (
        f"sha-{sha}-feature_widget"
    )
    assert tag_mod.push_latest("feature/widget") is False


def test_unsafe_branch_characters_become_underscores(tag_mod):
    sha = "c" * 40
    assert tag_mod.build_image_tag(sha, "fix: bad name") == f"sha-{sha}-fix__bad_name"


def test_tag_never_exceeds_registry_limit(tag_mod):
    sha = "d" * 40
    tag = tag_mod.build_image_tag(sha, "x" * 200)
    assert len(tag) <= 128
    assert tag.startswith(f"sha-{sha}-")


def test_non_hex_sha_is_rejected(tag_mod):
    with pytest.raises(ValueError):
        tag_mod.build_image_tag("not-a-sha", "main")


def test_manifest_records_branch_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "e" * 40)
    monkeypatch.setenv("GITHUB_REF_NAME", "feature/widget")
    monkeypatch.setenv("SERVICES_CSV", "core-api")
    monkeypatch.setenv("BUILD_ALL", "false")
    monkeypatch.delenv("IMAGE_TAG", raising=False)
    manifest = _load(MANIFEST_SCRIPT, "write_build_manifest")
    assert manifest.main() == 0
    data = json.loads((tmp_path / "dist" / "built-services.json").read_text())
    assert data["image_tag"] == f"sha-{'e' * 40}-feature_widget"


def test_ci_builds_every_push_and_gates_latest():
    source = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "branches: [main]" not in source
    assert "scripts/ci/image_tag.py" in source
    assert "PUSH_LATEST" in source
    assert 'TAG="sha-${GITHUB_SHA}"' not in source


def test_cd_uses_manifest_tag_and_stays_on_main():
    source = CD_WORKFLOW.read_text(encoding="utf-8")
    assert "branches: [main]" in source
    assert ".image_tag" in source
    assert "scripts/ci/image_tag.py" in source
    assert 'TAG="sha-${WORKFLOW_RUN_HEAD_SHA}"' not in source
    assert "sha-*" in source
