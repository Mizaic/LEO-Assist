"""Wave 3 unit tests for the calibrator helpers.

These tests exercise the pure-Python scoring + sweep logic without loading a
spaCy model. Full end-to-end calibration is covered by integration tests that
run the training job.
"""

from __future__ import annotations

import unittest

from app.calibrator import (
    LabelCalibration,
    _fit_isotonic,
    _metrics_at_threshold,
    _sweep_thresholds,
    apply_calibration,
)


class TestMetricsAtThreshold(unittest.TestCase):
    def test_perfect_separation(self):
        records = [
            (0.9, 1),
            (0.8, 1),
            (0.2, 0),
            (0.1, 0),
        ]
        f1, p, r = _metrics_at_threshold(records, 0.5)
        self.assertAlmostEqual(p, 1.0)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(f1, 1.0)

    def test_no_predictions_returns_zero(self):
        records = [(0.1, 1), (0.05, 0)]
        f1, p, r = _metrics_at_threshold(records, 0.9)
        self.assertEqual(p, 0.0)
        self.assertEqual(r, 0.0)
        self.assertEqual(f1, 0.0)

    def test_all_predicted_only_positives_hit(self):
        records = [(0.9, 1), (0.8, 0), (0.7, 0)]
        f1, p, r = _metrics_at_threshold(records, 0.5)
        self.assertAlmostEqual(p, 1 / 3)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(f1, 0.5)


class TestSweepThresholds(unittest.TestCase):
    def test_sweep_finds_optimal_threshold(self):
        # Positives cluster above 0.6, negatives below; optimal threshold is
        # somewhere in between.
        records = [
            (0.85, 1),
            (0.75, 1),
            (0.65, 1),
            (0.45, 0),
            (0.35, 0),
            (0.10, 0),
        ]
        thr, f1, p, r = _sweep_thresholds(records)
        self.assertGreater(f1, 0.9)
        self.assertGreaterEqual(thr, 0.45)
        self.assertLessEqual(thr, 0.70)

    def test_sweep_prefers_higher_f1(self):
        # Rare positive — lower threshold should win.
        records = [
            (0.3, 1),
            (0.2, 0),
            (0.1, 0),
        ]
        thr, f1, *_ = _sweep_thresholds(records)
        self.assertLessEqual(thr, 0.3)
        self.assertGreater(f1, 0.0)


class TestIsotonic(unittest.TestCase):
    def test_isotonic_returns_monotonic_curve(self):
        records = [
            (0.1, 0),
            (0.2, 0),
            (0.3, 0),
            (0.4, 1),
            (0.6, 1),
            (0.8, 1),
            (0.9, 1),
        ]
        xs, ys = _fit_isotonic(records)
        if not xs:
            self.skipTest("sklearn not available")
        # Check monotonic non-decreasing.
        for a, b in zip(ys, ys[1:]):
            self.assertLessEqual(a, b + 1e-6)


class TestApplyCalibration(unittest.TestCase):
    def test_returns_raw_when_no_curve(self):
        self.assertEqual(apply_calibration(0.7, {"isotonic_x": [], "isotonic_y": []}), 0.7)

    def test_interpolates_between_points(self):
        label_cal = {
            "isotonic_x": [0.0, 0.5, 1.0],
            "isotonic_y": [0.0, 0.3, 1.0],
        }
        self.assertAlmostEqual(apply_calibration(0.25, label_cal), 0.15, places=3)
        self.assertAlmostEqual(apply_calibration(0.75, label_cal), 0.65, places=3)

    def test_clips_outside_range(self):
        label_cal = {
            "isotonic_x": [0.1, 0.5, 0.9],
            "isotonic_y": [0.2, 0.5, 0.8],
        }
        self.assertEqual(apply_calibration(0.0, label_cal), 0.2)
        self.assertEqual(apply_calibration(1.0, label_cal), 0.8)


class TestLabelCalibrationToDict(unittest.TestCase):
    def test_roundtrip(self):
        cal = LabelCalibration(
            label="DISORDER",
            threshold=0.43,
            support_positive=120,
            support_negative=3400,
            f1_at_default=0.78,
            f1_at_threshold=0.82,
            precision_at_threshold=0.85,
            recall_at_threshold=0.79,
        )
        payload = cal.to_dict()
        self.assertEqual(payload["label"], "DISORDER")
        self.assertEqual(payload["threshold"], 0.43)
        self.assertEqual(payload["support_positive"], 120)
        self.assertEqual(payload["isotonic_x"], [])


if __name__ == "__main__":
    unittest.main()
