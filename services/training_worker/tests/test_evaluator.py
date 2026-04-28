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

            result = evaluator.evaluate_model(
                Path("/tmp/model-best"), Path("/tmp/dev.spacy")
            )

        self.assertEqual(result["precision"], 0.81)
        self.assertEqual(result["recall"], 0.79)
        self.assertEqual(result["f1"], 0.8)
        self.assertEqual(result["per_label"]["problem"]["precision"], 0.0)


class TestCheckLabelGates(unittest.TestCase):
    """Unit tests for _check_label_gates() and _load_label_min_f1().

    Covers DO-A35D2D57 ACs:
      - _check_label_gates() returns failure for every label below its floor
      - _check_label_gates() returns empty list when all labels pass
      - Labels absent from per_label are silently skipped
      - passed_gates=False and label_gate_failures non-empty on breach
      - LABEL_MIN_F1_JSON env var overrides individual floors
    """

    def _gates(self) -> dict[str, float]:
        from app.evaluator import _LABEL_MIN_F1_DEFAULTS
        return dict(_LABEL_MIN_F1_DEFAULTS)

    def test_returns_failure_for_label_below_floor(self):
        from app.evaluator import _check_label_gates
        per_label = {"DISORDER": {"f1": 0.70, "precision": 0.70, "recall": 0.70}}
        gates = {"DISORDER": 0.82}
        failures = _check_label_gates(per_label, gates)
        self.assertEqual(len(failures), 1)
        self.assertIn("DISORDER", failures[0])
        self.assertIn("0.700", failures[0])

    def test_returns_empty_when_all_pass(self):
        from app.evaluator import _check_label_gates
        per_label = {"DISORDER": {"f1": 0.90, "precision": 0.91, "recall": 0.89}}
        gates = {"DISORDER": 0.82}
        self.assertEqual(_check_label_gates(per_label, gates), [])

    def test_absent_label_is_skipped(self):
        from app.evaluator import _check_label_gates
        # DISORDER is in gates but not in per_label (not seen in dev split)
        failures = _check_label_gates({}, {"DISORDER": 0.82})
        self.assertEqual(failures, [])

    def test_low_support_label_is_reported_as_skip(self):
        from app.evaluator import _check_label_gates

        skips: list[str] = []
        failures = _check_label_gates(
            {"RECORD_ARTIFACT": {"f1": 0.0, "support": 3}},
            {"RECORD_ARTIFACT": 0.55},
            min_support=25,
            skipped=skips,
        )
        self.assertEqual(failures, [])
        self.assertEqual(len(skips), 1)
        self.assertIn("support=3", skips[0])

    def test_multiple_failures_all_returned(self):
        from app.evaluator import _check_label_gates
        per_label = {
            "DISORDER": {"f1": 0.50},
            "PROCEDURE": {"f1": 0.60},
            "FINDING": {"f1": 0.90},
        }
        gates = {"DISORDER": 0.82, "PROCEDURE": 0.80, "FINDING": 0.78}
        failures = _check_label_gates(per_label, gates)
        self.assertEqual(len(failures), 2)
        labels_failed = {f.split(":")[0] for f in failures}
        self.assertEqual(labels_failed, {"DISORDER", "PROCEDURE"})

    def test_label_min_f1_json_env_var_overrides_floor(self):
        import json
        from app.evaluator import _load_label_min_f1
        override = json.dumps({"DISORDER": 0.50})
        with patch.dict(os.environ, {"LABEL_MIN_F1_JSON": override}):
            merged = _load_label_min_f1()
        self.assertAlmostEqual(merged["DISORDER"], 0.50)
        # Unspecified labels keep their defaults
        self.assertAlmostEqual(merged["PROCEDURE"], 0.80)

    def test_label_min_f1_json_invalid_falls_back_to_defaults(self):
        from app.evaluator import _load_label_min_f1
        with patch.dict(os.environ, {"LABEL_MIN_F1_JSON": "not-json"}):
            merged = _load_label_min_f1()
        self.assertAlmostEqual(merged["DISORDER"], 0.82)

    def test_evaluate_model_fails_gates_on_label_breach(self):
        from app import evaluator

        logs: list[str] = []
        dev_docs = [_make_mock_doc() for _ in range(5)]
        dev_scores = {
            "ents_p": 0.92,
            "ents_r": 0.88,
            "ents_f": 0.90,
            "ents_per_type": {
                "DISORDER": {"p": 0.65, "r": 0.65, "f": 0.65},
            },
        }

        with (
            patch.object(evaluator, "_register_training_architectures"),
            patch("spacy.load", return_value=MagicMock()),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", return_value=dev_scores),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=[]),
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

        self.assertFalse(result["passed_gates"])
        self.assertGreater(len(result["label_gate_failures"]), 0)
        self.assertTrue(any("DISORDER" in m for m in logs if "LABEL GATE FAILED" in m))

    def test_evaluate_model_passes_when_all_labels_above_floor(self):
        from app import evaluator

        dev_docs = [_make_mock_doc() for _ in range(5)]
        # All gated labels well above their floors
        per_type = {
            lbl: {"p": 0.95, "r": 0.95, "f": 0.95}
            for lbl in evaluator._LABEL_MIN_F1_DEFAULTS
        }
        dev_scores = {
            "ents_p": 0.92,
            "ents_r": 0.88,
            "ents_f": 0.90,
            "ents_per_type": per_type,
        }

        with (
            patch.object(evaluator, "_register_training_architectures"),
            patch("spacy.load", return_value=MagicMock()),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", return_value=dev_scores),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=[]),
        ):
            instance = MagicMock()
            instance.get_docs.return_value = iter(dev_docs)
            mock_docbin_cls.return_value = instance
            instance.from_disk.return_value = instance
            result = evaluator.evaluate_model(
                Path("/tmp/model-best"), Path("/tmp/dev.spacy")
            )

        self.assertTrue(result["passed_gates"])
        self.assertEqual(result["label_gate_failures"], [])

    def test_evaluate_model_skips_low_support_label_gate(self):
        from app import evaluator

        logs: list[str] = []
        dev_docs = [_make_mock_doc() for _ in range(5)]
        dev_scores = {
            "ents_p": 0.92,
            "ents_r": 0.88,
            "ents_f": 0.90,
            "ents_per_type": {
                "RECORD_ARTIFACT": {"p": 0.0, "r": 0.0, "f": 0.0, "support": 3},
            },
        }

        with (
            patch.object(evaluator, "_register_training_architectures"),
            patch("spacy.load", return_value=MagicMock()),
            patch("spacy.tokens.DocBin") as mock_docbin_cls,
            patch.object(evaluator, "_score_examples", return_value=dev_scores),
            patch.object(evaluator, "_fetch_golden_set_docs", return_value=[]),
            patch.object(evaluator, "_MIN_LABEL_GATE_SUPPORT", 25),
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

        self.assertTrue(result["passed_gates"])
        self.assertEqual(result["label_gate_failures"], [])
        self.assertEqual(len(result["label_gate_skips"]), 1)
        self.assertIn("RECORD_ARTIFACT", result["label_gate_skips"][0])
        self.assertTrue(any("LABEL GATE SKIPPED" in m for m in logs))
