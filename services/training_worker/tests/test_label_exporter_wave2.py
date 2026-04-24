"""Wave 2 regression tests for label_exporter helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import spacy

from app.label_exporter import _record_to_spacy_doc, _resolve_split_ratios
from libs.training_ext.stratified_split import SplitRatios


class TestResolveSplitRatios(unittest.TestCase):
    def test_default_returns_70_10_10_10(self):
        ratios = _resolve_split_ratios(None, None)
        self.assertEqual(ratios.train, 0.7)
        self.assertEqual(ratios.val, 0.1)
        self.assertEqual(ratios.dev, 0.1)
        self.assertEqual(ratios.test, 0.1)

    def test_legacy_train_ratio_splits_remainder_equally(self):
        ratios = _resolve_split_ratios(0.8, None)
        self.assertAlmostEqual(ratios.train, 0.8, places=6)
        # remainder 0.2 split across val/dev/test.
        self.assertAlmostEqual(ratios.val + ratios.dev + ratios.test, 0.2, places=6)

    def test_explicit_ratios_take_priority(self):
        custom = SplitRatios(train=0.6, val=0.2, dev=0.1, test=0.1)
        ratios = _resolve_split_ratios(0.8, custom)
        self.assertIs(ratios, custom)

    def test_invalid_train_ratio_raises(self):
        with self.assertRaises(ValueError):
            _resolve_split_ratios(1.5, None)


class TestRecordToSpacyDocAlignmentReport(unittest.TestCase):
    def setUp(self):
        self.nlp = spacy.blank("en")

    def test_exact_span_leaves_report_empty(self):
        text = "Patient has diabetes"
        report: list = []
        entities = [
            {
                "text": "diabetes",
                "label": "DISORDER",
                "start": 12,
                "end": 20,
                "assertion": "present",
            }
        ]
        _record_to_spacy_doc(
            self.nlp, text, entities, alignment_report=report, label_id="GL-1"
        )
        self.assertEqual(report, [])

    def test_misaligned_span_records_before_and_after_offsets(self):
        text = "Patient has diabetes."
        # 11..19 cuts through "diabetes" — the expand mode will extend to the
        # full word boundary.
        report: list = []
        entities = [
            {
                "text": "diabetes",
                "label": "DISORDER",
                "start": 11,
                "end": 19,
                "assertion": "present",
            }
        ]
        _record_to_spacy_doc(
            self.nlp, text, entities, alignment_report=report, label_id="GL-2"
        )
        self.assertEqual(len(report), 1)
        entry = report[0]
        self.assertEqual(entry["label_id"], "GL-2")
        self.assertEqual(entry["label"], "DISORDER")
        self.assertEqual(entry["requested_start"], 11)
        self.assertEqual(entry["requested_end"], 19)
        # Resolved span should cover the full token.
        self.assertIn("diabetes", entry["resolved_surface"])


if __name__ == "__main__":
    unittest.main()
