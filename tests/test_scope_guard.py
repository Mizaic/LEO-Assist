"""Tests for libs.ner.scope_guard -- intended-use boundary enforcement."""

from __future__ import annotations

import pytest

from libs.ner.scope_guard import (
    SUPPRESSED,
    has_hedged_diagnosis,
    has_recommendation_language,
    is_safety_netting_sentence,
    reclassify_assertion,
)

# ---------------------------------------------------------------------------
# Safety-netting detection
# ---------------------------------------------------------------------------


class TestSafetyNettingDetection:
    def test_if_develops(self) -> None:
        assert is_safety_netting_sentence(
            "If you develop chest pain or shortness of breath, seek urgent medical attention"
        )

    def test_worsening_advice(self) -> None:
        assert is_safety_netting_sentence("Worsening advice given to patient")

    def test_attend_ae(self) -> None:
        assert is_safety_netting_sentence("Attend A&E immediately if symptoms worsen")

    def test_call_999(self) -> None:
        assert is_safety_netting_sentence(
            "Call 999 if you experience severe chest pain"
        )

    def test_call_111(self) -> None:
        assert is_safety_netting_sentence("Call 111 if symptoms do not improve")

    def test_red_flag(self) -> None:
        assert is_safety_netting_sentence("Red flag symptoms discussed with patient")

    def test_return_sooner_if(self) -> None:
        assert is_safety_netting_sentence(
            "Return sooner if symptoms worsen or new symptoms appear"
        )

    def test_ring_surgery_if(self) -> None:
        assert is_safety_netting_sentence(
            "Ring the surgery if not improving in 48 hours"
        )

    def test_normal_clinical_text_not_flagged(self) -> None:
        assert not is_safety_netting_sentence(
            "Patient presents with chest pain, onset 2 hours ago"
        )

    def test_diagnosis_not_flagged(self) -> None:
        assert not is_safety_netting_sentence("Diagnosis: community acquired pneumonia")

    def test_go_to_ae(self) -> None:
        assert is_safety_netting_sentence(
            "Go straight to A&E if breathing becomes difficult"
        )


# ---------------------------------------------------------------------------
# Treatment recommendation detection
# ---------------------------------------------------------------------------


class TestRecommendationDetection:
    def test_consider_starting(self) -> None:
        assert has_recommendation_language(
            "Consider starting metformin 500mg once daily"
        )

    def test_recommend_referral(self) -> None:
        assert has_recommendation_language("Recommend referral to cardiology")

    def test_advise_to_start(self) -> None:
        assert has_recommendation_language("Advised to start regular exercise")

    def test_suggest_initiating(self) -> None:
        assert has_recommendation_language("Suggest initiating statin therapy")

    def test_should_be_started_on(self) -> None:
        assert has_recommendation_language("Patient should be started on aspirin")

    def test_will_start_not_flagged(self) -> None:
        """'Will start' is ambiguous in UK GP notes — often means 'started today'."""
        assert not has_recommendation_language(
            "Will start amoxicillin 500mg TDS for 7 days"
        )

    def test_plan_to_refer(self) -> None:
        assert has_recommendation_language("Plan to refer to physiotherapy")

    def test_would_benefit_from(self) -> None:
        assert has_recommendation_language(
            "Would benefit from cognitive behavioural therapy"
        )

    def test_current_medication_not_flagged(self) -> None:
        assert not has_recommendation_language(
            "Currently taking metformin 500mg twice daily"
        )

    def test_procedure_done_not_flagged(self) -> None:
        assert not has_recommendation_language("Blood pressure checked, 140/90 mmHg")

    def test_active_diagnosis_not_flagged(self) -> None:
        assert not has_recommendation_language("Diagnosis: type 2 diabetes mellitus")


# ---------------------------------------------------------------------------
# Hedged diagnosis detection
# ---------------------------------------------------------------------------


class TestHedgedDiagnosis:
    def test_consistent_with(self) -> None:
        assert has_hedged_diagnosis(
            "Clinical picture consistent with viral upper respiratory infection"
        )

    def test_in_keeping_with(self) -> None:
        assert has_hedged_diagnosis("Symptoms in keeping with gastroesophageal reflux")

    def test_suggestive_of(self) -> None:
        assert has_hedged_diagnosis("Presentation suggestive of migraine")

    def test_may_represent(self) -> None:
        assert has_hedged_diagnosis("Rash may represent contact dermatitis")

    def test_cannot_exclude(self) -> None:
        assert has_hedged_diagnosis("Cannot exclude pulmonary embolism")

    def test_differential_includes(self) -> None:
        assert has_hedged_diagnosis("Differential includes cellulitis and DVT")

    def test_confirmed_diagnosis_overrides(self) -> None:
        assert not has_hedged_diagnosis(
            "Consistent with pneumonia, diagnosis confirmed on chest X-ray"
        )

    def test_explicit_diagnosis_overrides(self) -> None:
        assert not has_hedged_diagnosis(
            "Suggestive of UTI -- diagnosis: urinary tract infection"
        )

    def test_plain_diagnosis_not_flagged(self) -> None:
        assert not has_hedged_diagnosis("Diagnosis: community acquired pneumonia")

    def test_raises_possibility(self) -> None:
        assert has_hedged_diagnosis("Raises the possibility of malignancy")


# ---------------------------------------------------------------------------
# reclassify_assertion -- integrated logic
# ---------------------------------------------------------------------------


class TestReclassifyAssertion:
    def test_safety_netting_returns_suppressed(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="If you develop chest pain, call 999",
        )
        assert result == SUPPRESSED

    def test_safety_netting_suppressed_not_hypothetical(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="If you develop chest pain, call 999",
        )
        assert result != "hypothetical"

    def test_recommendation_reclassifies_to_hypothetical(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="Consider starting metformin 500mg",
        )
        assert result == "hypothetical"

    def test_hedged_diagnosis_reclassifies_to_possible(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="Presentation suggestive of migraine",
        )
        assert result == "possible"

    def test_hedged_diagnosis_only_affects_disorder(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="Presentation suggestive of migraine",
        )
        assert result is None

    def test_already_absent_not_changed(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="absent",
            sentence_text="If you develop chest pain, call 999",
        )
        assert result is None

    def test_already_hypothetical_not_changed(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="hypothetical",
            sentence_text="Consider starting metformin 500mg",
        )
        assert result is None

    def test_normal_present_disorder_unchanged(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="Diagnosis: community acquired pneumonia",
        )
        assert result is None

    def test_normal_substance_unchanged(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="Currently taking atorvastatin 20mg daily",
        )
        assert result is None

    def test_medication_instruction_indication_is_suppressed(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="finding",
            entity_assertion="present",
            sentence_text="Fluoxetine 20mg capsules - take two daily for low mood",
            entity_text="low mood",
        )
        assert result == SUPPRESSED

    def test_medication_entity_not_suppressed_by_instruction_phrase(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="Fluoxetine 20mg capsules - take two daily for low mood",
            entity_text="Fluoxetine 20mg capsules",
        )
        assert result is None

    def test_side_effect_counselling_finding_is_suppressed(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="finding",
            entity_assertion="present",
            sentence_text=(
                "Advised at increased risk of s/e such as dizziness, drowsiness, "
                "breathing changes, constipation, blurred vision - advised to look "
                "out for these and report back to surgery"
            ),
            entity_text="dizziness",
        )
        assert result == SUPPRESSED

    def test_side_effect_counselling_does_not_suppress_unrelated_procedure(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="procedure",
            entity_assertion="present",
            sentence_text=(
                "Advised at increased risk of s/e such as dizziness, drowsiness - "
                "advised to look out for these and report back to surgery"
            ),
            entity_text="Telephone consultation",
        )
        assert result is None

    def test_will_start_medication_not_reclassified(self) -> None:
        """'Will start' is too ambiguous in UK GP notes — no reclassification."""
        result = reclassify_assertion(
            entity_semantic_tag="substance",
            entity_assertion="present",
            sentence_text="Will start amoxicillin 500mg TDS for 7 days",
        )
        assert result is None

    def test_plan_to_refer_is_hypothetical(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="procedure",
            entity_assertion="present",
            sentence_text="Plan to refer to physiotherapy",
        )
        assert result == "hypothetical"

    def test_safety_netting_suppresses_all_tags(self) -> None:
        for tag in ("disorder", "substance", "procedure", "finding"):
            result = reclassify_assertion(
                entity_semantic_tag=tag,
                entity_assertion="present",
                sentence_text="Call 999 if you experience severe chest pain",
            )
            assert (
                result == SUPPRESSED
            ), f"Expected SUPPRESSED for tag {tag}, got {result!r}"

    def test_raises_suspicion_reclassifies_disorder(self) -> None:
        result = reclassify_assertion(
            entity_semantic_tag="disorder",
            entity_assertion="present",
            sentence_text="Raises the suspicion of malignancy",
        )
        assert result == "possible"
