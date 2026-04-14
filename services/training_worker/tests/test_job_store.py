"""Tests for TrainingJob.to_dict() per-label metrics shortcut.

Covers VT-LEO-AI-106-TC-003.
"""

import unittest

from app.job_store import TrainingJob


class TestJobStoreToDictMetrics(unittest.TestCase):
    """VT-106-TC-003: per_label_f1 top-level shortcut."""

    def _make_job_with_metrics(self) -> TrainingJob:
        job = TrainingJob(triggered_by="test")
        job.metrics = {
            "ner": {
                "precision": 0.85,
                "recall": 0.80,
                "f1": 0.82,
                "per_label": {
                    "DISORDER": {"precision": 0.90, "recall": 0.85, "f1": 0.87},
                    "FINDING": {"precision": 0.78, "recall": 0.72, "f1": 0.75},
                },
                "passed_gates": True,
                "dev_doc_count": 20,
            },
            "export": {
                "total": 99,
                "assertion_filtered": 3,
                "span_misaligned": 1,
            },
        }
        return job

    def test_per_label_f1_at_top_level(self):
        job = self._make_job_with_metrics()
        d = job.to_dict()
        self.assertIn("per_label_f1", d)
        self.assertIsInstance(d["per_label_f1"], dict)
        self.assertIn("DISORDER", d["per_label_f1"])

    def test_precision_recall_f1_shortcuts(self):
        job = self._make_job_with_metrics()
        d = job.to_dict()
        self.assertAlmostEqual(d["precision"], 0.85)
        self.assertAlmostEqual(d["recall"], 0.80)
        self.assertAlmostEqual(d["f1"], 0.82)

    def test_export_counters_at_top_level(self):
        job = self._make_job_with_metrics()
        d = job.to_dict()
        self.assertEqual(d["export_total"], 99)
        self.assertEqual(d["export_assertion_filtered"], 3)
        self.assertEqual(d["export_span_misaligned"], 1)

    def test_empty_metrics_does_not_raise(self):
        job = TrainingJob(triggered_by="test")
        try:
            d = job.to_dict()
        except Exception as exc:
            self.fail(f"to_dict() raised with empty metrics: {exc}")
        self.assertIsNone(d["precision"])
        self.assertEqual(d["per_label_f1"], {})
