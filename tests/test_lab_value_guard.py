"""Tests for the lab-value guard that prevents diagnostic inference from lab results.

Covers the critical safety scenario: eGFR 69 mL/min must NOT be coded as
CKD stage 1 — only as an observable entity.
"""

from __future__ import annotations

import pytest

from libs.ner.lab_value_guard import (
    filter_inferred_diagnoses,
    is_lab_result_sentence,
    should_suppress_disorder,
)
from libs.ner.precision_gates import check_entity


# ---------------------------------------------------------------------------
# is_lab_result_sentence
# ---------------------------------------------------------------------------


class TestIsLabResultSentence:
    def test_egfr_with_value(self) -> None:
        assert is_lab_result_sentence(
            "eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 69 mL/min"
        )

    def test_sodium_with_value(self) -> None:
        assert is_lab_result_sentence("Serum sodium level (XE2q0) 142 mmol/L [135 - 145]")

    def test_haemoglobin_with_value(self) -> None:
        assert is_lab_result_sentence("Haemoglobin concentration (Xa96v) 106 g/L [130-180]")

    def test_creatinine_with_value(self) -> None:
        assert is_lab_result_sentence("Creatinine 115 umol/L")

    def test_hba1c_with_value(self) -> None:
        assert is_lab_result_sentence("HbA1c 48 mmol/mol")

    def test_plain_text_not_lab(self) -> None:
        assert not is_lab_result_sentence("Patient has type 2 diabetes mellitus")

    def test_lab_name_without_value_not_lab(self) -> None:
        assert not is_lab_result_sentence("Check sodium levels next week")

    def test_diagnosis_text_not_lab(self) -> None:
        assert not is_lab_result_sentence("Chronic kidney disease stage 3")


# ---------------------------------------------------------------------------
# should_suppress_disorder — CKD-EPI formula confusion
# ---------------------------------------------------------------------------


class TestSuppressCKDFromFormula:
    EGFR_SENTENCE = (
        "eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 69 mL/min"
    )

    def test_ckd_disorder_from_egfr_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="CKD",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease stage 1",
            sentence_text=self.EGFR_SENTENCE,
        )

    def test_ckd_stage1_from_egfr_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="Chronic kidney disease stage 1",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease stage 1",
            sentence_text=self.EGFR_SENTENCE,
        )

    def test_kidney_disease_from_egfr_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="kidney disease",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease",
            sentence_text=self.EGFR_SENTENCE,
        )

    def test_renal_failure_from_egfr_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="renal failure",
            entity_semantic_tag="disorder",
            entity_normalized="renal failure",
            sentence_text=self.EGFR_SENTENCE,
        )

    def test_observable_entity_not_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="eGFR using creatinine (CKD-EPI) per 1.73 square metres",
            entity_semantic_tag="observable entity",
            entity_normalized="estimated glomerular filtration rate",
            sentence_text=self.EGFR_SENTENCE,
        )

    def test_egfr_with_low_value(self) -> None:
        low_egfr = "eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 25 mL/min"
        assert should_suppress_disorder(
            entity_text="CKD stage 4",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease stage 4",
            sentence_text=low_egfr,
        )


# ---------------------------------------------------------------------------
# should_suppress_disorder — general lab value inference
# ---------------------------------------------------------------------------


class TestSuppressInferredDiagnoses:
    def test_diabetes_from_hba1c_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="diabetes mellitus",
            entity_semantic_tag="disorder",
            entity_normalized="diabetes mellitus",
            sentence_text="HbA1c 48 mmol/mol",
        )

    def test_hyponatraemia_from_sodium_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="hyponatraemia",
            entity_semantic_tag="disorder",
            entity_normalized="hyponatraemia",
            sentence_text="Sodium 129 mmol/L",
        )

    def test_anaemia_from_haemoglobin_suppressed(self) -> None:
        assert should_suppress_disorder(
            entity_text="anaemia",
            entity_semantic_tag="disorder",
            entity_normalized="anaemia",
            sentence_text="Haemoglobin concentration (Xa96v) 106 g/L [130-180]",
        )

    def test_disorder_with_numeric_value_fields_suppressed(self) -> None:
        """If LLM returns a disorder entity with value/unit, it's from a lab line."""
        assert should_suppress_disorder(
            entity_text="chronic kidney disease",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease",
            sentence_text="eGFR using creatinine (CKD-EPI) 69 mL/min",
            entity_numeric_value="69",
            entity_unit="mL/min",
        )


# ---------------------------------------------------------------------------
# should_suppress_disorder — entities that must NOT be suppressed
# ---------------------------------------------------------------------------


class TestDoNotSuppressLegitimateDisorders:
    def test_explicit_diagnosis_not_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="chronic kidney disease stage 3",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease stage 3",
            sentence_text="Diagnosis: chronic kidney disease stage 3, eGFR 43 mL/min",
        )

    def test_disorder_in_non_lab_sentence_not_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="type 2 diabetes mellitus",
            entity_semantic_tag="disorder",
            entity_normalized="type 2 diabetes mellitus",
            sentence_text="Patient has type 2 diabetes mellitus",
        )

    def test_disorder_in_problem_list_not_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="hypertension",
            entity_semantic_tag="disorder",
            entity_normalized="hypertension",
            sentence_text="Problem list: hypertension, type 2 diabetes",
        )

    def test_observable_entity_never_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="eGFR",
            entity_semantic_tag="observable entity",
            entity_normalized="estimated glomerular filtration rate",
            sentence_text="eGFR 69 mL/min",
        )

    def test_substance_never_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="metformin",
            entity_semantic_tag="substance",
            entity_normalized="metformin",
            sentence_text="Creatinine 115 umol/L, on metformin",
        )

    def test_ckd_as_standalone_diagnosis_not_suppressed(self) -> None:
        assert not should_suppress_disorder(
            entity_text="CKD stage 3",
            entity_semantic_tag="disorder",
            entity_normalized="chronic kidney disease stage 3",
            sentence_text="CKD stage 3, under renal team",
        )


# ---------------------------------------------------------------------------
# filter_inferred_diagnoses — batch filtering
# ---------------------------------------------------------------------------


class TestFilterInferredDiagnoses:
    def test_filters_disorder_keeps_observable(self) -> None:
        sentence = "eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 69 mL/min"
        entities = [
            {
                "text": "eGFR using creatinine (CKD-EPI) per 1.73 square metres",
                "label": "observable_entity",
                "normalized": "estimated glomerular filtration rate",
                "value": "69",
                "unit": "mL/min",
            },
            {
                "text": "CKD",
                "label": "disorder",
                "normalized": "chronic kidney disease stage 1",
            },
        ]
        filtered = filter_inferred_diagnoses(sentence, entities)
        assert len(filtered) == 1
        assert filtered[0]["label"] == "observable_entity"

    def test_keeps_all_when_no_lab_context(self) -> None:
        sentence = "Patient has type 2 diabetes and hypertension"
        entities = [
            {
                "text": "type 2 diabetes",
                "label": "disorder",
                "normalized": "type 2 diabetes mellitus",
            },
            {
                "text": "hypertension",
                "label": "disorder",
                "normalized": "hypertension",
            },
        ]
        filtered = filter_inferred_diagnoses(sentence, entities)
        assert len(filtered) == 2

    def test_empty_entities_returns_empty(self) -> None:
        assert filter_inferred_diagnoses("eGFR 69 mL/min", []) == []


# ---------------------------------------------------------------------------
# precision_gates.check_entity — CKD-EPI formula detection
# ---------------------------------------------------------------------------


class TestPrecisionGatesCKDEPI:
    EGFR_SENTENCE = (
        "eGFR using creatinine (CKD-EPI) per 1.73 square metres (XacUK) 69 mL/min"
    )

    def test_ckd_disorder_from_ckd_epi_rejected(self) -> None:
        entity = {"text": "CKD", "label": "disorder", "domain": ""}
        reasons = check_entity(entity, self.EGFR_SENTENCE)
        assert "ckd_extracted_from_ckd_epi_formula" in reasons

    def test_chronic_kidney_disease_from_ckd_epi_rejected(self) -> None:
        entity = {"text": "chronic kidney disease", "label": "disorder", "domain": ""}
        reasons = check_entity(entity, self.EGFR_SENTENCE)
        assert "ckd_extracted_from_ckd_epi_formula" in reasons

    def test_ckd_without_ckd_epi_not_rejected(self) -> None:
        entity = {"text": "CKD", "label": "disorder", "domain": ""}
        reasons = check_entity(entity, "CKD stage 3, under renal team")
        assert "ckd_extracted_from_ckd_epi_formula" not in reasons

    def test_observable_entity_not_rejected(self) -> None:
        entity = {"text": "eGFR", "label": "observable_entity", "domain": ""}
        reasons = check_entity(entity, self.EGFR_SENTENCE)
        assert "ckd_extracted_from_ckd_epi_formula" not in reasons

    def test_renal_failure_from_ckd_epi_rejected(self) -> None:
        entity = {"text": "renal failure", "label": "disorder", "domain": ""}
        reasons = check_entity(entity, self.EGFR_SENTENCE)
        assert "ckd_extracted_from_ckd_epi_formula" in reasons
