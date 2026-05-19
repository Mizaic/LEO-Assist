"""Tests for label_exporter span realignment, assertion filtering, multi-label.

Covers VT-LEO-AI-106-TC-001, VT-LEO-AI-106-TC-002, and
VT-LEO-AI-107-TC-001 (multi-label export to doc.spans["sc"]).
VT-LEO-AI-106-TC-003: diagnostics collection for dropped entities.
"""

import os
import unittest
from unittest.mock import patch

import spacy

from libs.pipeline.label_filter import (
    DEFAULT_EXCLUDED_ASSERTIONS,
    filter_and_realign,
    get_excluded_assertions,
    realign_entity,
)
from app.label_exporter import (
    _DEFAULT_EXCLUDED_ASSERTIONS,
    _add_doc_candidate_coverage,
    _candidate_coverage_report,
    _filter_entities_to_training_labels,
    _new_candidate_coverage,
    _filter_and_realign,
    _get_excluded_assertions,
    _excluded_training_sources,
    _included_training_labels,
    _realign_entity,
    _record_to_spacy_doc,
)
from libs.training_data.gold_granularity import safe_for_training_export


class TestRealignEntity(unittest.TestCase):
    """VT-106-TC-001: span realignment."""

    def _make_ent(self, text: str, label: str = "DISORDER") -> dict:
        return {
            "text": text,
            "label": label,
            "start": 0,
            "end": 0,
            "assertion": "present",
        }

    def test_surface_not_found_returns_none(self):
        ent = self._make_ent("hypertension")
        result = _realign_entity("Patient has diabetes", ent)
        self.assertIsNone(result)

    def test_surface_found_corrects_offsets(self):
        ent = self._make_ent("diabetes")
        result = _realign_entity("Patient has diabetes", ent)
        self.assertIsNotNone(result)
        text = "Patient has diabetes"
        expected_start = text.index("diabetes")
        expected_end = expected_start + len("diabetes")
        self.assertEqual(result["start"], expected_start)
        self.assertEqual(result["end"], expected_end)

    def test_empty_surface_text_returns_none(self):
        ent = {"text": "", "label": "DISORDER", "start": 0, "end": 5}
        result = _realign_entity("Patient has diabetes", ent)
        self.assertIsNone(result)

    def test_no_exception_on_missing_surface(self):
        ent = self._make_ent("xyzzy_not_present_123")
        try:
            _realign_entity("Short sentence here", ent)
        except Exception as exc:
            self.fail(f"_realign_entity raised unexpected exception: {exc}")


class TestFilterAndRealign(unittest.TestCase):
    """VT-106-TC-002: assertion filtering."""

    def _present(self, surface: str) -> dict:
        return {
            "text": surface,
            "label": "DISORDER",
            "start": 0,
            "end": 0,
            "assertion": "present",
        }

    def _negated(self, surface: str) -> dict:
        return {
            "text": surface,
            "label": "DISORDER",
            "start": 0,
            "end": 0,
            "assertion": "negated",
        }

    def test_negated_entity_excluded_when_explicit_set_passed(self):
        # DEFAULT_EXCLUDED_ASSERTIONS is intentionally empty (assertions are
        # handled by the ConText engine post-extraction, not the training filter).
        # Callers must pass an explicit set to exclude assertions.
        text = "Patient has diabetes but no hypertension"
        entities = [self._present("diabetes"), self._negated("hypertension")]
        filtered, assertion_filtered, span_misaligned = _filter_and_realign(
            text, entities, {"negated"}
        )
        self.assertEqual(assertion_filtered, 1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["text"], "diabetes")

    def test_default_excluded_assertions_is_empty(self):
        # By design: no assertions are excluded unless TRAINING_EXCLUDE_ASSERTIONS
        # is set. The ConText engine handles assertion post-extraction.
        from libs.pipeline.label_filter import DEFAULT_EXCLUDED_ASSERTIONS
        self.assertEqual(DEFAULT_EXCLUDED_ASSERTIONS, frozenset())

    def test_default_excluded_assertions_env_unset_returns_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRAINING_EXCLUDE_ASSERTIONS", None)
            exclusions = _get_excluded_assertions()
        self.assertEqual(exclusions, set())

    def test_custom_exclusions_from_env(self):
        with patch.dict(
            os.environ, {"TRAINING_EXCLUDE_ASSERTIONS": "negated,uncertain"}
        ):
            exclusions = _get_excluded_assertions()
        self.assertIn("negated", exclusions)
        self.assertIn("uncertain", exclusions)
        self.assertNotIn("hypothetical", exclusions)

    def test_present_entity_passes_through(self):
        text = "Patient has diabetes"
        entities = [self._present("diabetes")]
        filtered, assertion_filtered, span_misaligned = _filter_and_realign(
            text, entities, _DEFAULT_EXCLUDED_ASSERTIONS
        )
        self.assertEqual(assertion_filtered, 0)
        self.assertEqual(len(filtered), 1)

    def test_span_misalign_counted_when_surface_missing(self):
        text = "Patient has diabetes"
        entities = [
            {
                "text": "xyzzy_missing",
                "label": "DISORDER",
                "start": 0,
                "end": 5,
                "assertion": "present",
            }
        ]
        filtered, assertion_filtered, span_misaligned = _filter_and_realign(
            text, entities, _DEFAULT_EXCLUDED_ASSERTIONS
        )
        self.assertEqual(span_misaligned, 1)
        self.assertEqual(len(filtered), 0)


class TestRecordToSpacyDocMultiLabel(unittest.TestCase):
    """VT-107-TC-001: multi-label export writes to doc.spans['sc']."""

    def setUp(self):
        self.nlp = spacy.blank("en")

    def _make_ent(self, text: str, label: str, start: int, end: int) -> dict:
        return {
            "text": text,
            "label": label,
            "start": start,
            "end": end,
            "assertion": "present",
        }

    def test_uses_spans_sc_not_ents(self):
        text = "Patient has diabetes"
        ents = [self._make_ent("diabetes", "DISORDER", 12, 20)]
        doc = _record_to_spacy_doc(self.nlp, text, ents)
        self.assertIn("sc", doc.spans)
        self.assertEqual(len(doc.spans["sc"]), 1)

    def test_two_labels_same_span_both_written(self):
        text = "Furosemide increased to 40mg BD"
        start, end = 0, len("Furosemide increased to 40mg BD")
        ents = [
            self._make_ent(text, "MEDICINAL_PRODUCT", start, end),
            self._make_ent(text, "PROCEDURE", start, end),
        ]
        doc = _record_to_spacy_doc(self.nlp, text, ents)
        self.assertEqual(len(doc.spans["sc"]), 2)
        labels = {s.label_ for s in doc.spans["sc"]}
        self.assertIn("MEDICINAL_PRODUCT", labels)
        self.assertIn("PROCEDURE", labels)

    def test_nested_overlapping_spans_both_written(self):
        text = "breast lesion with mets"
        ents = [
            self._make_ent("breast lesion", "DISORDER", 0, 13),
            self._make_ent("breast lesion with mets", "DISORDER", 0, 23),
            self._make_ent("breast lesion with mets", "FINDING", 0, 23),
        ]
        doc = _record_to_spacy_doc(self.nlp, text, ents)
        self.assertEqual(len(doc.spans["sc"]), 3)

    def test_empty_entities_produces_empty_sc(self):
        text = "Administrative only"
        doc = _record_to_spacy_doc(self.nlp, text, [])
        self.assertIn("sc", doc.spans)
        self.assertEqual(len(doc.spans["sc"]), 0)


class TestCandidateCoverageDiagnostics(unittest.TestCase):
    """Candidate coverage proves whether gold spans are proposable."""

    def setUp(self):
        self.nlp = spacy.blank("en")

    def test_reports_contract_coverage_by_label_and_split(self):
        text = " ".join(f"w{i}" for i in range(12))
        entities = [
            {"label": "OBSERVABLE", "start": 0, "end": len(text)},
            {"label": "PROCEDURE", "start": 0, "end": len("w0 w1")},
        ]
        doc = _record_to_spacy_doc(self.nlp, text, entities)
        coverage = _new_candidate_coverage(["val"])

        _add_doc_candidate_coverage(coverage, "val", doc)
        report = _candidate_coverage_report(coverage)

        self.assertEqual(report["narrow"]["val"]["OBSERVABLE"]["covered"], 0)
        self.assertEqual(report["broad_1_24"]["val"]["OBSERVABLE"]["covered"], 1)
        self.assertEqual(report["balanced"]["val"]["PROCEDURE"]["covered"], 1)


class TestTrainingLabelScope(unittest.TestCase):
    def test_default_scope_includes_target_labels_only(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRAINING_INCLUDED_LABELS", None)
            labels = _included_training_labels()

        self.assertEqual(labels, {"PROCEDURE", "OBSERVABLE", "FINDING", "SITUATION"})

    def test_default_scope_excludes_synthetic_and_lab_coder_sources(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRAINING_EXCLUDED_SOURCES", None)
            sources = _excluded_training_sources()

        self.assertEqual(
            sources,
            {
                "lab_coder_v1",
                "synthetic",
                "synthetic_rare_label_remediation_20260428",
            },
        )

    def test_filters_entities_to_target_labels(self):
        entities = [
            {"label": "PROCEDURE", "text": "CT"},
            {"label": "observable_entity", "text": "haemoglobin"},
            {"label": "DISORDER", "text": "asthma"},
        ]

        kept = _filter_entities_to_training_labels(
            entities,
            {"PROCEDURE", "OBSERVABLE"},
        )

        self.assertEqual([ent["text"] for ent in kept], ["CT", "haemoglobin"])
        self.assertEqual([ent["label"] for ent in kept], ["PROCEDURE", "OBSERVABLE"])

    def test_export_guard_blocks_quarantined_and_long_partial_records(self):
        entities = [{"label": "PROCEDURE", "text": "xray", "start": 20, "end": 24}]

        self.assertFalse(
            safe_for_training_export(
                "History: cough\nPlan: xray requested",
                entities,
            )
        )
        self.assertFalse(
            safe_for_training_export(
                "xray requested",
                entities,
                training_quarantined=True,
            )
        )
        self.assertTrue(
            safe_for_training_export(
                "Plan: xray requested",
                [{"label": "PROCEDURE", "text": "xray", "start": 6, "end": 10}],
                annotation_completeness="derived_sentence",
            )
        )


class TestFilterAndRealignDiagnostics(unittest.TestCase):
    """VT-106-TC-003: per-entity diagnostics collection."""

    def _present(self, surface: str) -> dict:
        return {
            "text": surface,
            "label": "DISORDER",
            "start": 0,
            "end": 0,
            "assertion": "present",
        }

    def _negated(self, surface: str) -> dict:
        return {
            "text": surface,
            "label": "DISORDER",
            "start": 0,
            "end": 0,
            "assertion": "negated",
        }

    def test_no_assertion_filtered_when_default_empty(self):
        # DEFAULT_EXCLUDED_ASSERTIONS is empty by design; passing it should
        # not filter any entities — that is the contract.
        text = "Patient has diabetes but no hypertension"
        entities = [self._present("diabetes"), self._negated("hypertension")]
        result, n_assert, _ = filter_and_realign(
            text, entities, set(DEFAULT_EXCLUDED_ASSERTIONS)
        )
        self.assertEqual(n_assert, 0)
        self.assertEqual(len(result), 2)

    def test_assertion_filtered_appended_to_diagnostics(self):
        # Pass an explicit exclusion set to exercise the diagnostic path.
        text = "Patient has diabetes but no hypertension"
        entities = [self._present("diabetes"), self._negated("hypertension")]
        diagnostics: list = []
        filter_and_realign(
            text,
            entities,
            {"negated"},
            diagnostics=diagnostics,
            label_id="GL-001",
            source="test_source",
        )
        self.assertEqual(len(diagnostics), 1)
        dropped = diagnostics[0]
        self.assertEqual(dropped["label_id"], "GL-001")
        self.assertEqual(dropped["source"], "test_source")
        self.assertEqual(dropped["entity_text"], "hypertension")
        self.assertEqual(dropped["assertion"], "negated")
        self.assertEqual(dropped["reason"], "assertion_filtered")
        # The drop-entry uses key "text" (the sentence), not "sentence".
        self.assertNotIn("sentence", dropped)
        self.assertIn("text", dropped)

    def test_span_misaligned_appended_with_text(self):
        # The drop-entry dict uses key "text" for the sentence, not "sentence".
        text = "Patient has diabetes"
        entities = [
            {
                "text": "not_in_sentence",
                "label": "DISORDER",
                "start": 0,
                "end": 5,
                "assertion": "present",
            }
        ]
        diagnostics: list = []
        filter_and_realign(
            text,
            entities,
            set(DEFAULT_EXCLUDED_ASSERTIONS),
            diagnostics=diagnostics,
            label_id="GL-002",
            source="test_source",
        )
        self.assertEqual(len(diagnostics), 1)
        dropped = diagnostics[0]
        self.assertEqual(dropped["reason"], "span_misaligned")
        self.assertEqual(dropped["text"], text)
        self.assertEqual(dropped["label_id"], "GL-002")

    def test_multiple_drops_all_captured(self):
        text = "Patient has diabetes"
        entities = [
            self._negated("hypertension"),
            {
                "text": "xyzzy_missing",
                "label": "DISORDER",
                "start": 0,
                "end": 5,
                "assertion": "present",
            },
            self._present("diabetes"),
        ]
        diagnostics: list = []
        # Use an explicit exclusion set so negated is actually filtered.
        kept, n_assert, n_span = filter_and_realign(
            text,
            entities,
            {"negated"},
            diagnostics=diagnostics,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(n_assert, 1)
        self.assertEqual(n_span, 1)
        self.assertEqual(len(diagnostics), 2)
        reasons = {d["reason"] for d in diagnostics}
        self.assertIn("assertion_filtered", reasons)
        self.assertIn("span_misaligned", reasons)

    def test_legacy_alias_passes_through_with_empty_exclusions(self):
        # _filter_and_realign is the alias imported from label_exporter.
        # With empty default exclusions, nothing is assertion-filtered.
        text = "Patient has diabetes but no hypertension"
        entities = [self._present("diabetes"), self._negated("hypertension")]
        result, n_assert, n_span = _filter_and_realign(
            text, entities, set(_DEFAULT_EXCLUDED_ASSERTIONS)
        )
        self.assertEqual(n_assert, 0)
        self.assertEqual(len(result), 2)
