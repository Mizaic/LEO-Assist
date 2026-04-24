"""End-to-end regression tests for Wave 0-5 integration points."""

from __future__ import annotations

import json

from libs.training_ext.bundle import assemble_bundle, verify_bundle
from libs.training_ext.feature_flags import FLAGS
from libs.training_ext.inference_calibration import load_calibration


def test_bundle_and_inference_calibration_roundtrip(tmp_path):
    """A model dir assembled by the training worker must load cleanly into
    the inference service with a verified manifest."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "meta.json").write_text(json.dumps({"performance": {"spans_sc_f": 0.82}}))
    (model_dir / "calibration.json").write_text(
        json.dumps(
            {
                "default_threshold": 0.5,
                "per_label": {
                    "DISORDER": {"threshold": 0.42, "isotonic_x": [], "isotonic_y": []},
                    "FINDING": {"threshold": 0.63, "isotonic_x": [], "isotonic_y": []},
                },
                "macro_f1_before": 0.78,
                "macro_f1_after": 0.82,
            }
        )
    )

    manifest = assemble_bundle(
        model_dir,
        version="20260424-reg1",
        dataset_hash="dataset-abc",
        extras={"git": "feedbabe"},
    )
    assert "calibration.json" in manifest.file_hashes

    issues = verify_bundle(model_dir)
    assert issues == []

    loaded = load_calibration(model_dir)
    assert loaded.is_verified is True
    assert loaded.threshold_for("DISORDER") == 0.42
    assert loaded.threshold_for("UNKNOWN") == 0.5


def test_every_wave_has_at_least_one_flag():
    waves_with_flags = {f.wave for f in FLAGS}
    # Waves 0/2 introduce no user-facing env flags, so they are allowed to be
    # absent.  Waves 1, 3, 4, 5 must each contribute at least one.
    for required in (1, 3, 4, 5):
        assert required in waves_with_flags, f"wave {required} missing feature flag"
