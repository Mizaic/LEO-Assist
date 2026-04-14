"""Tests for multi-label post-processing nesting suppression refinement.

Covers VT-LEO-AI-107-TC-003 and VT-LEO-AI-107-TC-004:
- Layer 5 normalise_entity_types preserves nested same-label spans when
  normalized lookup terms differ.
- Layer 5 suppresses nested same-label spans when normalized terms are
  identical (the original redundancy behaviour is preserved).
"""

from __future__ import annotations

import unittest

from libs.pipeline.post_processing import normalise_entity_types


def _ent(
    text: str,
    label: str,
    start: int,
    end: int,
    normalized: str = "",
) -> dict:
    return {
        "text": text,
        "label": label,
        "start": start,
        "end": end,
        "normalized": normalized or text.lower(),
        "assertion": "present",
    }


class TestNestingSuppressionRefined(unittest.TestCase):
    """VT-107-TC-003: layer 5 nesting suppression conditioned on normalized."""

    def test_different_normalized_both_preserved(self):
        entities = [
            _ent(
                "breast lesion",
                "disorder",
                0,
                13,
                normalized="lesion of breast",
            ),
            _ent(
                "breast lesion with mets",
                "disorder",
                0,
                23,
                normalized="malignant neoplasm of breast",
            ),
        ]
        normalise_entity_types(entities)
        self.assertEqual(len(entities), 2, "Both spans should survive")
        texts = {e["text"] for e in entities}
        self.assertIn("breast lesion", texts)
        self.assertIn("breast lesion with mets", texts)

    def test_identical_normalized_nested_span_suppressed(self):
        entities = [
            _ent("T2 N1", "staging_scale", 0, 5, normalized="t2 n1"),
            _ent("T2 N1 M0", "staging_scale", 0, 8, normalized="t2 n1"),
        ]
        normalise_entity_types(entities)
        self.assertEqual(len(entities), 1, "Identical normalized: nested span suppressed")
        self.assertEqual(entities[0]["text"], "T2 N1 M0")

    def test_same_span_different_labels_both_preserved(self):
        entities = [
            _ent(
                "breast lesion with mets",
                "disorder",
                0,
                23,
                normalized="malignant neoplasm of breast",
            ),
            _ent(
                "breast lesion with mets",
                "finding",
                0,
                23,
                normalized="clinical stage iv",
            ),
        ]
        normalise_entity_types(entities)
        self.assertEqual(len(entities), 2, "Different labels: both spans preserved")
        labels = {e["label"] for e in entities}
        self.assertIn("disorder", labels)
        self.assertIn("finding", labels)

    def test_exact_duplicate_same_label_same_normalized_suppressed(self):
        entities = [
            _ent("diabetes", "disorder", 0, 8, normalized="type 2 diabetes mellitus"),
            _ent("diabetes", "disorder", 0, 8, normalized="type 2 diabetes mellitus"),
        ]
        normalise_entity_types(entities)
        self.assertEqual(len(entities), 1, "Exact duplicate should be suppressed")


class TestFullBreastLesionPipeline(unittest.TestCase):
    """VT-107-TC-004: three-span breast lesion case survives layer 5."""

    def test_three_spans_all_preserved(self):
        entities = [
            _ent("breast lesion", "disorder", 0, 13, normalized="lesion of breast"),
            _ent(
                "breast lesion with mets",
                "disorder",
                0,
                23,
                normalized="malignant neoplasm of breast",
            ),
            _ent(
                "breast lesion with mets",
                "finding",
                0,
                23,
                normalized="clinical stage iv",
            ),
        ]
        normalise_entity_types(entities)
        self.assertEqual(
            len(entities),
            3,
            "All three spans must survive post-processing layer 5",
        )
        texts = [e["text"] for e in entities]
        labels = [e["label"] for e in entities]
        self.assertIn("breast lesion", texts)
        self.assertEqual(texts.count("breast lesion with mets"), 2)
        self.assertIn("disorder", labels)
        self.assertIn("finding", labels)
