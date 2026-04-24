"""Wave 5 tests for the artifact bundle helpers."""

from __future__ import annotations

import json
from pathlib import Path

from libs.training_ext.bundle import (
    assemble_bundle,
    verify_bundle,
)


def test_assemble_bundle_hashes_all_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "calibration.json").write_text(json.dumps({"default_threshold": 0.5}))
    (source / "orth_variants.json").write_text(json.dumps({"single": [], "paired": []}))

    model = tmp_path / "model"
    model.mkdir()
    (model / "meta.json").write_text("{}")

    manifest = assemble_bundle(
        model,
        version="20260424-150000",
        source_dir=source,
        dataset_hash="dataset-hash-abc",
        extras={"git": "deadbeef"},
    )
    assert manifest.model_version == "20260424-150000"
    assert manifest.dataset_hash == "dataset-hash-abc"
    # Sidecars should have been copied into the model dir.
    assert (model / "calibration.json").exists()
    assert (model / "orth_variants.json").exists()
    # The manifest itself is not in its own file_hashes.
    assert "bundle_manifest.json" not in manifest.file_hashes
    assert "calibration.json" in manifest.file_hashes
    assert "meta.json" in manifest.file_hashes


def test_verify_bundle_detects_tampering(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "meta.json").write_text("original")
    assemble_bundle(model, version="1", dataset_hash="hash")
    assert verify_bundle(model) == []

    # Tamper.
    (model / "meta.json").write_text("tampered")
    issues = verify_bundle(model)
    assert len(issues) == 1
    assert "meta.json" in issues[0]


def test_verify_bundle_detects_missing_file(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "meta.json").write_text("x")
    assemble_bundle(model, version="1", dataset_hash="hash")

    (model / "meta.json").unlink()
    issues = verify_bundle(model)
    assert any("missing file" in i for i in issues)


def test_verify_bundle_without_manifest_returns_warning(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    assert verify_bundle(model) == ["bundle_manifest.json missing"]
