"""Unit tests for TREATMENT_HISTORY leaf evaluation.

Atlas trace: VT-B60E3046
"""

import pytest

from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator


class TestTreatmentHistoryMatches:
    def _eval(self, node, facts):
        return GuidelineEvaluator._treatment_history_matches(node, facts)

    def test_failed_ppi_matches(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "failed",
                  "duration_days": 28, "source_ids": ["enc-5"]}]
        matched, reason, src = self._eval(node, facts)
        assert matched is True
        assert src == ["enc-5"]

    def test_not_tolerated_matches(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "not_tolerated",
                  "source_ids": ["enc-6"]}]
        matched, reason, src = self._eval(node, facts)
        assert matched is True

    def test_planned_does_not_match(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "planned"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_ongoing_does_not_match(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "ongoing"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_completed_does_not_match(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "completed"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_unknown_outcome_fails_closed(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "unknown"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
        assert "fail closed" in reason.lower()

    def test_empty_list_fails_closed(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        matched, reason, _ = self._eval(node, [])
        assert matched is False
        assert "fail closed" in reason.lower()

    def test_min_duration_met_matches(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI",
                "min_duration_days": 28}
        facts = [{"treatment_class": "PPI", "outcome": "failed", "duration_days": 28}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is True

    def test_min_duration_not_met_does_not_match(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI",
                "min_duration_days": 28}
        facts = [{"treatment_class": "PPI", "outcome": "failed", "duration_days": 7}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_missing_duration_when_min_required_fails_closed(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI",
                "min_duration_days": 28}
        facts = [{"treatment_class": "PPI", "outcome": "failed",
                  "duration_days": None}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
        assert "fail closed" in reason.lower()

    def test_wrong_treatment_class_does_not_match(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "H2RA", "outcome": "failed"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
