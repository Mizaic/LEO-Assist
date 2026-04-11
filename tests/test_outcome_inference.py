"""
VT-LEO-AI-088 -- Post-specialist outcome inference engine unit tests.

Covers all 5 verdict branches, confidence formula, earliest-date capture,
confidence cap at 0.95, and episode status immutability guard.

Design controls: DI-LEO-AI-088, R-LEO-AI-062, VT-LEO-AI-088
"""

from __future__ import annotations

import pytest

from libs.pipeline.outcome_inference import (
    ENCOUNTER_EXCLUSIONS,
    InferenceResult,
    score_post_specialist_encounters,
    _CLEAR_CAP,
    _WEAK_CAP,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enc(date: str, text: str = "", flags: str = "") -> dict:
    return {"date": date, "text": text, "flags": flags}


# ---------------------------------------------------------------------------
# VT-088-TC-001: Clear benign verdict
# ---------------------------------------------------------------------------


class TestClearBenign:
    def test_verdict(self):
        rows = [
            _enc(
                "2024-10-01",
                text="Patient discharged from clinic, no further follow-up required.",
            ),
            _enc("2024-10-15", text="Reassured, routine review in 6 months."),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "INFERRED_BENIGN"

    def test_inferred_outcome(self):
        rows = [_enc("2024-10-01", text="discharged from clinic")]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"

    def test_confidence_range(self):
        rows = [_enc("2024-10-01", text="discharged from clinic. Reassured patient.")]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_confidence is not None
        assert 0.60 <= result.inferred_confidence <= _CLEAR_CAP

    def test_earliest_date(self):
        rows = [
            _enc("2024-10-05", text="admin only, no signal"),
            _enc("2024-10-15", text="Efudix cream prescribed once daily"),
            _enc("2024-11-01", text="discharged"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome_date == "2024-10-15"

    def test_signals_populated(self):
        rows = [_enc("2024-10-01", text="discharged. Reassured patient.")]
        result = score_post_specialist_encounters(rows)
        assert len(result.inference_signals) > 0


# ---------------------------------------------------------------------------
# VT-088-TC-002: Clear cancer verdict
# ---------------------------------------------------------------------------


class TestClearCancer:
    def test_verdict(self):
        rows = [
            _enc("2024-10-01", text="Excision of lesion booked at surgical clinic."),
            _enc("2024-10-15", text="Pathology result confirmed malignant tissue."),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "INFERRED_CANCER"

    def test_inferred_outcome(self):
        rows = [_enc("2024-10-01", text="surgical excision of lesion performed")]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "cancer"

    def test_confidence_range(self):
        rows = [
            _enc(
                "2024-10-01",
                text="pathology result confirmed malignant. Oncology referral sent.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_confidence is not None
        assert 0.60 <= result.inferred_confidence <= _CLEAR_CAP


# ---------------------------------------------------------------------------
# VT-088-TC-003: Weak cancer verdict (mixed signals, cancer dominant)
# ---------------------------------------------------------------------------


class TestWeakCancer:
    def test_verdict(self):
        rows = [
            _enc(
                "2024-10-01",
                text="Pathology result received confirming malignancy. Oncology referral. Histology result returned.",
            ),
            _enc("2024-10-15", text="discharged from follow-up"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "INFERRED_CANCER_WEAK"
        assert result.inferred_outcome == "cancer"

    def test_confidence_capped_at_weak_cap(self):
        rows = [
            _enc(
                "2024-10-01",
                text="Pathology result received confirming malignancy. Oncology referral. Histology result returned.",
            ),
            _enc("2024-10-15", text="discharged from follow-up"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_confidence is not None
        assert result.inferred_confidence <= _WEAK_CAP


# ---------------------------------------------------------------------------
# VT-088-TC-004: HITL required -- no signals
# ---------------------------------------------------------------------------


class TestHITLRequired:
    def test_empty_rows(self):
        result = score_post_specialist_encounters([])
        assert result.verdict == "HITL_REQUIRED"
        assert result.inferred_outcome is None
        assert result.inferred_confidence is None
        assert result.inferred_outcome_date is None

    def test_rows_with_no_signal_text(self):
        rows = [
            _enc("2024-10-01", text="Administration event. Record keeping."),
            _enc("2024-10-15", text="Telephone call, no clinical content."),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "HITL_REQUIRED"
        assert result.inferred_outcome is None

    def test_equal_signals_returns_hitl(self):
        # Exactly 1 cancer signal vs exactly 1 benign signal -> HITL (ambiguous)
        rows = [
            _enc("2024-10-01", text="radiotherapy course started"),  # 1 cancer signal
            _enc("2024-10-15", text="discharged from clinic"),  # 1 benign signal
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "HITL_REQUIRED"
        assert result.inferred_outcome is None


# ---------------------------------------------------------------------------
# VT-088-TC-005: Earliest signal date captured
# ---------------------------------------------------------------------------


class TestEarliestDate:
    def test_earliest_date_across_multiple_encounters(self):
        rows = [
            _enc("2024-10-01", text="administration only"),
            _enc("2024-10-15", text="Efudix cream prescribed"),  # first signal
            _enc("2024-11-01", text="discharged from clinic"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome_date == "2024-10-15"

    def test_cancer_date_from_first_cancer_signal(self):
        rows = [
            _enc("2024-09-01", text="no signal"),
            _enc("2024-09-20", text="pathology result: carcinoma confirmed"),
            _enc("2024-10-05", text="oncology referral sent"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome_date == "2024-09-20"

    def test_date_none_when_no_signals(self):
        rows = [_enc("2024-10-01", text="administration only")]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome_date is None


# ---------------------------------------------------------------------------
# VT-088-TC-006: Confidence cap at 0.95
# ---------------------------------------------------------------------------


class TestConfidenceCap:
    def test_many_benign_signals_capped(self):
        rows = [
            _enc(
                f"2024-{str(m).zfill(2)}-01",
                text="discharged from clinic. Reassured. No further follow-up. AK actinic keratosis. Efudix prescribed. Reassured again.",
            )
            for m in range(1, 13)
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_confidence is not None
        assert result.inferred_confidence <= _CLEAR_CAP

    def test_many_cancer_signals_capped(self):
        rows = [
            _enc(
                f"2024-{str(m).zfill(2)}-01",
                text="excision booked. Oncology referral. Pathology result. Histology. Malignant carcinoma. Radiotherapy.",
            )
            for m in range(1, 13)
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_confidence is not None
        assert result.inferred_confidence <= _CLEAR_CAP


# ---------------------------------------------------------------------------
# VT-088-TC-007: Episode status immutability guard
# ---------------------------------------------------------------------------


class TestStatusImmutability:
    def test_inference_update_query_does_not_mutate_status(self):
        """_INFERENCE_UPDATE_Q must never SET ep.status."""
        from services.analysis_worker.app.analyzers import episode_builder

        q = episode_builder._INFERENCE_UPDATE_Q
        assert (
            "ep.status" not in q
        ), "_INFERENCE_UPDATE_Q must not set ep.status -- inference is additive metadata only"


# ---------------------------------------------------------------------------
# INFERRED_BENIGN_WEAK branch
# ---------------------------------------------------------------------------


class TestWeakBenign:
    def test_verdict(self):
        rows = [
            _enc(
                "2024-10-01",
                text="discharged. Reassured. No further follow-up. AK treatment.",
            ),
            _enc("2024-10-15", text="pathology result confirmed malignant tissue"),
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "INFERRED_BENIGN_WEAK"
        assert result.inferred_outcome == "benign"
        assert result.inferred_confidence is not None
        assert result.inferred_confidence <= _WEAK_CAP


# ---------------------------------------------------------------------------
# InferenceResult fields completeness
# ---------------------------------------------------------------------------


class TestInferenceResultFields:
    def test_all_fields_present_for_cancer(self):
        rows = [
            _enc(
                "2024-10-01",
                text="excision of lesion booked. Pathology result received confirmed malignant.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert isinstance(result, InferenceResult)
        assert result.verdict is not None
        assert result.inferred_outcome is not None
        assert result.inferred_outcome_date is not None
        assert result.inferred_confidence is not None
        assert isinstance(result.inference_signals, list)
        assert len(result.inference_signals) > 0

    def test_signals_list_empty_for_hitl(self):
        result = score_post_specialist_encounters([])
        assert result.inference_signals == []


# ---------------------------------------------------------------------------
# Cross-pathway contamination prevention (regression tests from April 2026
# investigation of head & neck and lung stale episode false positives)
# ---------------------------------------------------------------------------


class TestExclusionContexts:
    def test_cataract_surgery_excluded(self):
        """Excision signal in cataract surgery must not count as cancer signal."""
        rows = [
            _enc(
                "2024-10-15",
                text="phakoemulsification of cataract performed. Lens implant. Excision of posterior capsule.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert (
            result.verdict == "HITL_REQUIRED"
        ), "Cataract encounter should be excluded entirely"

    def test_vascular_malformation_excision_excluded(self):
        """Excision of vascular malformation (hand surgery) must not fire cancer signal."""
        rows = [
            _enc(
                "2024-10-15",
                text="Excision of vascular malformation of left hand. Skin lesion photography.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert (
            result.verdict == "HITL_REQUIRED"
        ), "Vascular malformation excision should be excluded"

    def test_miu_discharge_excluded(self):
        """Discharged from minor injuries unit must not count as pathway closure."""
        rows = [
            _enc(
                "2024-10-15",
                text="Attended minor injuries unit. Discharged home. No follow-up required.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.verdict == "HITL_REQUIRED", "MIU discharge should be excluded"

    def test_unrelated_encounter_does_not_block_valid_cancer_signal(self):
        """A cataract encounter should be excluded but a separate cancer signal encounter should still count."""
        rows = [
            _enc(
                "2024-10-01",
                text="phakoemulsification of cataract. Discharged from ophthalmology.",
            ),
            _enc(
                "2024-10-15",
                text="Oncology referral sent. Pathology result confirmed malignant tissue.",
            ),
        ]
        result = score_post_specialist_encounters(rows)
        assert (
            result.inferred_outcome == "cancer"
        ), "Valid cancer signals from non-excluded encounter should still fire"


class TestTightenedCancerSignals:
    def test_bare_excision_word_no_longer_fires(self):
        """'excision' alone (without cancer-relevant object) must NOT fire cancer signal."""
        rows = [_enc("2024-10-15", text="excision performed at hand clinic")]
        result = score_post_specialist_encounters(rows)
        assert "excision of lesion" not in (result.inference_signals or [])

    def test_pathology_request_no_longer_fires(self):
        """'Pathology' in the context of a blood/monitoring request must NOT fire."""
        rows = [
            _enc(
                "2024-10-15",
                text="Pathology request sent for TSH and thyroid function. Carbimazole dose adjusted.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert (
            result.inferred_outcome != "cancer"
        ), "Pathology request (not result) should not fire cancer signal"

    def test_pathology_result_fires(self):
        """'Pathology result' with explicit result context MUST fire."""
        rows = [
            _enc("2024-10-15", text="Pathology result received confirming carcinoma.")
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "cancer"

    def test_histology_result_fires(self):
        """'Histology result' with explicit result context MUST fire."""
        rows = [
            _enc("2024-10-15", text="Histology report confirmed malignant melanoma.")
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "cancer"

    def test_excision_of_cancer_lesion_fires(self):
        """'Excision of lesion' (cancer-relevant object) MUST fire."""
        rows = [_enc("2024-10-15", text="Wide local excision of melanoma booked.")]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "cancer"


class TestBenignENTAndRespiratorySignals:
    def test_normal_larynx_fires_benign(self):
        rows = [
            _enc(
                "2024-10-15",
                text="Diagnostic nasendoscopy performed. Normal larynx. No abnormality detected.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"

    def test_laryngopharyngeal_reflux_fires_benign(self):
        rows = [
            _enc(
                "2024-10-15",
                text="Diagnosis: laryngopharyngeal reflux. Lansoprazole prescribed. Routine follow up.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"

    def test_chronic_rhinitis_fires_benign(self):
        rows = [
            _enc(
                "2024-10-15",
                text="ENT outcome: chronic rhinitis. No malignancy identified. Discharged.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"

    def test_emphysema_fires_benign(self):
        rows = [
            _enc(
                "2024-10-15",
                text="New episode emphysema coded. COPD management plan initiated.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"

    def test_fibroadenoma_fires_benign(self):
        rows = [
            _enc(
                "2024-10-15",
                text="Ultrasound-guided biopsy confirmed fibroadenoma. No evidence of cancer. Discharged.",
            )
        ]
        result = score_post_specialist_encounters(rows)
        assert result.inferred_outcome == "benign"


class TestSiteMapFixes:
    def test_thyroid_maps_to_head_and_neck(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert _extract_condition_key("Thyroid cancer (disorder)") == "head_and_neck"
        assert _extract_condition_key("Goitre") == "head_and_neck"
        assert _extract_condition_key("Carcinoma of pharynx") == "head_and_neck"
        assert _extract_condition_key("Laryngeal carcinoma") == "head_and_neck"

    def test_myelofibrosis_maps_to_haematological(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert _extract_condition_key("Primary myelofibrosis") == "haematological"
        assert _extract_condition_key("Myeloproliferative disorder") == "haematological"
        assert _extract_condition_key("Essential thrombocythaemia") == "haematological"

    def test_generic_cancer_maps_to_non_site_specific_not_unknown(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert _extract_condition_key("Malignant neoplasm") == "non_site_specific"
        assert _extract_condition_key("Suspected malignancy") == "non_site_specific"
        assert _extract_condition_key("Carcinoma NOS") == "non_site_specific"

    def test_truly_unknown_still_returns_unknown(self):
        from services.analysis_worker.app.analyzers.episode_builder import (
            _extract_condition_key,
        )

        assert _extract_condition_key("Administrative entry") == "unknown"
        assert _extract_condition_key("Blood pressure monitoring") == "unknown"
