"""Wave 4 tests for the pseudo-labeller configuration parser."""

from __future__ import annotations

import json

import pytest

from libs.training_ext.pseudo_labeller import PseudoLabelingConfig


def test_defaults(monkeypatch):
    for key in (
        "PSEUDO_LABEL_MIN_CONFIDENCE",
        "PSEUDO_LABEL_MAX_SPANS_PER_DOC",
        "PSEUDO_LABEL_THRESHOLDS_JSON",
        "PSEUDO_LABEL_SKIP_LABELS",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = PseudoLabelingConfig.from_env()
    assert cfg.min_confidence == pytest.approx(0.85)
    assert cfg.max_spans_per_doc == 100
    assert cfg.per_label_thresholds == {}
    assert cfg.skip_labels == frozenset()


def test_per_label_thresholds_parsed(monkeypatch):
    monkeypatch.setenv(
        "PSEUDO_LABEL_THRESHOLDS_JSON",
        json.dumps({"DISORDER": 0.95, "observable": 0.8}),
    )
    cfg = PseudoLabelingConfig.from_env()
    assert cfg.per_label_thresholds["DISORDER"] == pytest.approx(0.95)
    assert cfg.per_label_thresholds["OBSERVABLE"] == pytest.approx(0.8)
    assert cfg.threshold_for("DISORDER") == pytest.approx(0.95)
    assert cfg.threshold_for("SUBSTANCE") == pytest.approx(0.85)


def test_skip_labels_normalised(monkeypatch):
    monkeypatch.setenv("PSEUDO_LABEL_SKIP_LABELS", "temporal, frequency ")
    cfg = PseudoLabelingConfig.from_env()
    assert "TEMPORAL" in cfg.skip_labels
    assert "FREQUENCY" in cfg.skip_labels


def test_bad_json_ignored(monkeypatch):
    monkeypatch.setenv("PSEUDO_LABEL_THRESHOLDS_JSON", "not-json")
    cfg = PseudoLabelingConfig.from_env()
    assert cfg.per_label_thresholds == {}
