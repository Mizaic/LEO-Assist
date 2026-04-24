"""Wave 5 tests for the inference-time calibration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass

from libs.training_ext.bundle import assemble_bundle
from libs.training_ext.inference_calibration import (
    InferenceCalibration,
    filter_and_rescore,
    load_calibration,
)


@dataclass
class _FakeSpan:
    label_: str
    start_char: int
    end_char: int
    text: str
    kb_id_: str


def _build_calibration_fixture(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    payload = {
        "default_threshold": 0.5,
        "per_label": {
            "DISORDER": {
                "threshold": 0.4,
                "isotonic_x": [0.0, 0.5, 1.0],
                "isotonic_y": [0.0, 0.3, 1.0],
            },
            "FINDING": {
                "threshold": 0.7,
                "isotonic_x": [],
                "isotonic_y": [],
            },
        },
    }
    (model_dir / "calibration.json").write_text(json.dumps(payload))
    assemble_bundle(model_dir, version="v1", dataset_hash="h")
    return model_dir


def test_load_calibration_reads_file_and_verifies(tmp_path):
    model_dir = _build_calibration_fixture(tmp_path)
    cal = load_calibration(model_dir)
    assert cal.default_threshold == 0.5
    assert cal.threshold_for("disorder") == 0.4
    assert cal.threshold_for("FINDING") == 0.7
    assert cal.threshold_for("UNKNOWN") == 0.5
    assert cal.is_verified is True


def test_load_calibration_handles_missing_file(tmp_path):
    cal = load_calibration(tmp_path)
    assert cal.default_threshold == 0.5
    assert cal.per_label == {}


def test_calibrate_interpolates_isotonic(tmp_path):
    cal = load_calibration(_build_calibration_fixture(tmp_path))
    assert abs(cal.calibrate("DISORDER", 0.5) - 0.3) < 1e-6
    assert cal.calibrate("DISORDER", 0.0) == 0.0
    # Labels without isotonic breakpoints return the raw score.
    assert cal.calibrate("FINDING", 0.9) == 0.9


def test_filter_and_rescore_drops_low_confidence_spans():
    cal = InferenceCalibration(
        default_threshold=0.5,
        per_label={"DISORDER": {"threshold": 0.4}},
    )
    spans = [
        _FakeSpan("DISORDER", 0, 5, "hello", "0.6"),
        _FakeSpan("DISORDER", 6, 10, "ouch", "0.3"),  # below threshold -> drop
        _FakeSpan("FINDING", 11, 20, "tachy", "0.9"),
    ]
    out = filter_and_rescore(spans, cal)
    assert len(out) == 2
    assert {s.label for s in out} == {"DISORDER", "FINDING"}
    assert all(s.raw_score >= cal.threshold_for(s.label) for s in out)


def test_filter_includes_below_threshold_when_asked():
    cal = InferenceCalibration(default_threshold=0.9)
    spans = [_FakeSpan("FINDING", 0, 4, "abcd", "0.1")]
    out = filter_and_rescore(spans, cal, include_below_threshold=True)
    assert len(out) == 1
