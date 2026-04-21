"""Tests for `libs/classifiers/encounter_classifier.py`.

Atlas trace:
  DO: DO-0FB8F15D
  DI: DI-FBCCD265

Verifies:
  - classify_encounter wraps the rule-based textcat into a ClassificationResult
  - clinical_significance follows content_type
  - build_patient_encounter_index correctly tallies admin/document/clinical
  - empty encounter text shortcircuits to admin_only without calling textcat
  - checkpoint cache is honoured when available
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.classifiers.encounter_classifier import (
    ClassificationResult,
    PatientEncounterIndex,
    build_patient_encounter_index,
    classify_encounter,
)


class TestClassifyEncounter:
    def test_clinical_text_is_marked_medium_significance(self):
        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            return_value="clinical",
        ):
            r = classify_encounter("Patient has chest pain")
        assert r.content_type == "clinical"
        assert r.clinical_significance == "medium"
        assert r.consensus_agreement is True
        assert r.model_a_type == "rule_textcat"

    def test_admin_text_is_marked_low_significance(self):
        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            return_value="admin_only",
        ):
            r = classify_encounter("Letter received")
        assert r.content_type == "admin_only"
        assert r.clinical_significance == "low"

    def test_document_transfer_is_marked_low_significance(self):
        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            return_value="document_transfer",
        ):
            r = classify_encounter("Discharge summary attached")
        assert r.content_type == "document_transfer"
        assert r.clinical_significance == "low"


class TestBuildIndex:
    def test_returns_index_for_empty_encounter_list(self):
        idx = build_patient_encounter_index("PAT-1", [])
        assert isinstance(idx, PatientEncounterIndex)
        assert idx.patient_id == "PAT-1"
        assert idx.total == 0
        assert idx.admin_count == 0
        assert idx.clinical_count == 0

    def test_empty_text_short_circuits_to_admin_only(self):
        with patch(
            "libs.classifiers.encounter_classifier.classify_text"
        ) as mock_classify:
            idx = build_patient_encounter_index(
                "PAT-2",
                [{"encounter_id": "E1", "text": ""},
                 {"encounter_id": "E2", "text": "   "}],
            )
        mock_classify.assert_not_called()
        assert idx.admin_count == 2
        assert idx.classifications["E1"].content_type == "admin_only"
        assert idx.classifications["E2"].content_type == "admin_only"

    def test_tallies_each_content_type_once(self):
        def _classify(text):
            return {
                "admin": "admin_only",
                "document": "document_transfer",
                "clinical": "clinical",
            }[text]

        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            side_effect=_classify,
        ):
            idx = build_patient_encounter_index(
                "PAT-3",
                [
                    {"encounter_id": "A", "text": "admin"},
                    {"encounter_id": "D", "text": "document"},
                    {"encounter_id": "C1", "text": "clinical"},
                    {"encounter_id": "C2", "text": "clinical"},
                ],
            )
        assert idx.total == 4
        assert idx.admin_count == 1
        assert idx.document_transfer_count == 1
        assert idx.clinical_count == 2

    def test_uses_id_when_encounter_id_missing(self):
        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            return_value="clinical",
        ):
            idx = build_patient_encounter_index(
                "PAT-4", [{"id": "ENC-99", "text": "headache"}]
            )
        assert "ENC-99" in idx.classifications

    def test_checkpoint_cache_hit_skips_classifier(self):
        store = MagicMock()
        cached = {
            "content_type": "clinical",
            "domains": ["cardiology"],
            "encounter_purpose": [],
            "key_clinical_signals": [],
            "expected_semantic_tags": [],
            "clinical_significance": "medium",
            "consensus_agreement": True,
            "model_a_type": "rule_textcat",
            "model_b_type": "",
        }
        store.get.return_value = cached

        with patch(
            "libs.classifiers.encounter_classifier.classify_text"
        ) as mock_classify:
            idx = build_patient_encounter_index(
                "PAT-5",
                [{"encounter_id": "E1", "text": "anything"}],
                checkpoint_store=store,
            )
        mock_classify.assert_not_called()
        assert idx.classifications["E1"].content_type == "clinical"
        assert idx.domain_summary == {"cardiology": 1}

    def test_checkpoint_miss_writes_after_classifying(self):
        store = MagicMock()
        store.get.return_value = None
        with patch(
            "libs.classifiers.encounter_classifier.classify_text",
            return_value="clinical",
        ):
            build_patient_encounter_index(
                "PAT-6",
                [{"encounter_id": "E1", "text": "headache"}],
                checkpoint_store=store,
            )
        store.set.assert_called_once()
        key = store.set.call_args.args[0]
        assert key == "classify:PAT-6:E1"
