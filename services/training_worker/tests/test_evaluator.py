"""Tests for evaluator golden gate and per-label metrics.

Covers VT-LEO-AI-106-TC-005.
spaCy load and DocBin are patched so no trained model is needed.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import spacy


def _make_mock_doc(text: str = "Patient has diabetes"):
    """Minimal mock spaCy Doc."""
    doc = MagicMock()
    doc.text = text
    doc.ents = []
    return doc


class TestGoldenGate(unittest.TestCase):
    """VT-106-TC-005: golden gate fails job below threshold."""

    def _run_evaluate(
        self,
        golden_f1: float = 0.80,
        min_golden_f1: float = 0.70,
        golden_docs_count: int = 5,
    ) -> tuple[dict, list[str]]:
        from app import evaluator

        logs: list[str] = []

        dev_docs = [_make_mock_doc() for _ in range(10)]
        golden_docs = [_make_mock_doc() for _ in range(golden_docs_count)]

        dev_scores = {
            "ents_p": 0.92,
            "ents_r": 0.88,
            "ents_f": 0.90,
            "ents_per_type": {},
        }
        golden_scores = {
            "ents_p": golden_f1,
            "ents_r": golden_f1,
            "ents_f": golden_f1,
            "ents_per_type": {},
        }

        mock_nlp = MagicMock()
        mock_docbin = MagicMock()
        mock_docbin.get_docs.return_value = iter(dev_docs)

        score_side_effects = (
            [dev_scores, golden_scores] if golden_docs_count else [dev_scores]
        )

        with (
            patch.dict(os.environ, {"MODEL_MIN_GOLDEN_F1": str(min_golden_f1)}),
            patch("spacy.load", return_value=mock_nlp),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", side_effect=score_side_effects),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=golden_docs),
            patch.object(evaluator, "_MIN_GOLDEN_F1", min_golden_f1),
        ):
            instance = MagicMock()
            instance.get_docs.return_value = iter(dev_docs)
            mock_docbin_cls.return_value = instance
            instance.from_disk.return_value = instance

            result = evaluator.evaluate_model(
                Path("/tmp/model-best"),
                Path("/tmp/dev.spacy"),
                log_fn=logs.append,
            )

        return result, logs

    def test_golden_gate_fails_job_below_threshold(self):
        result, logs = self._run_evaluate(golden_f1=0.50, min_golden_f1=0.70)
        self.assertFalse(result["passed_gates"])
        self.assertFalse(result["golden_passed"])
        fail_logs = [m for m in logs if "GOLDEN GATE FAILED" in m]
        self.assertTrue(len(fail_logs) > 0, "Expected GOLDEN GATE FAILED in logs")

    def test_golden_gate_passes_above_threshold(self):
        result, _ = self._run_evaluate(golden_f1=0.80, min_golden_f1=0.70)
        self.assertTrue(result["golden_passed"])

    def test_golden_metrics_in_result(self):
        result, _ = self._run_evaluate(golden_f1=0.80, min_golden_f1=0.70)
        for key in (
            "golden_precision",
            "golden_recall",
            "golden_f1",
            "golden_passed",
            "golden_doc_count",
        ):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_no_golden_docs_skips_gate(self):
        result, logs = self._run_evaluate(golden_docs_count=0)
        self.assertNotIn("golden_f1", result)
        skip_logs = [m for m in logs if "skipping" in m.lower()]
        self.assertTrue(len(skip_logs) > 0, "Expected 'skipping' message in logs")

    def test_registers_training_architectures_before_model_load(self):
        from app import evaluator

        call_order: list[str] = []
        dev_docs = [_make_mock_doc() for _ in range(2)]
        dev_scores = {"ents_p": 0.9, "ents_r": 0.9, "ents_f": 0.9, "ents_per_type": {}}

        def _mark_registered() -> None:
            call_order.append("register")

        def _mock_load(_path: str):
            call_order.append("load")
            return MagicMock()

        with (
            patch.object(
                evaluator,
                "_register_training_architectures",
                side_effect=_mark_registered,
            ),
            patch("spacy.load", side_effect=_mock_load),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", return_value=dev_scores),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=[]),
        ):
            instance = MagicMock()
            instance.get_docs.return_value = iter(dev_docs)
            mock_docbin_cls.return_value = instance
            instance.from_disk.return_value = instance
            evaluator.evaluate_model(Path("/tmp/model-best"), Path("/tmp/dev.spacy"))

        self.assertEqual(call_order, ["register", "load"])

    def test_none_span_scores_fall_back_to_entity_scores(self):
        from app import evaluator

        dev_docs = [_make_mock_doc() for _ in range(2)]
        dev_scores = {
            "spans_sc_p": None,
            "spans_sc_r": None,
            "spans_sc_f": None,
            "ents_p": 0.81,
            "ents_r": 0.79,
            "ents_f": 0.80,
            "ents_per_type": {"problem": {"p": None, "r": 0.5, "f": 0.6}},
        }

        with (
            patch("spacy.load", return_value=MagicMock()),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", return_value=dev_scores),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=[]),
        ):
            instance = MagicMock()
            instance.get_docs.return_value = iter(dev_docs)
            mock_docbin_cls.return_value = instance
            instance.from_disk.return_value = instance

            result = evaluator.evaluate_model(Path("/tmp/model-best"), Path("/tmp/dev.spacy"))

        self.assertEqual(result["precision"], 0.81)
        self.assertEqual(result["recall"], 0.79)
        self.assertEqual(result["f1"], 0.8)
        self.assertEqual(result["per_label"]["problem"]["precision"], 0.0)
