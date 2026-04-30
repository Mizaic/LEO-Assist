"""Unit tests for libs/oncology/prior_consultations.

Covers the deterministic pre-filter (``is_clinical_contact``), the
contact-type classifier (``classify_contact_type``), the LLM response
parser (``parse_llm_response``), and the end-to-end orchestrator
(``classify_episode_consultations``) with a mocked LLM caller.

Test fixtures are drawn from the live cancer cohort (patients
4469113522, 4940120139, 4200797127, 6044092682, 7324271383) so the
NCDA factor heuristics are exercised against real GP record text
shapes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from libs.oncology.prior_consultations import (
    NCDA_FACTOR_LABELS,
    NCDA_FACTORS_AUTO_DETECTABLE,
    NCDA_FACTORS_HUMAN_REVIEW_ONLY,
    NCDA_FACTORS_LLM_JUDGMENT,
    CandidateEncounter,
    ConsultationVerdict,
    FactorVerdict,
    PriorConsultationsResult,
    build_user_message,
    classify_contact_type,
    classify_episode_consultations,
    empty_result_for_no_candidates,
    is_clinical_contact,
    parse_llm_response,
    select_candidate_encounters,
)


# ---------------------------------------------------------------------------
# Pre-filter: is_clinical_contact
# ---------------------------------------------------------------------------


class TestIsClinicalContact:
    def test_empty_text_is_not_a_contact(self) -> None:
        assert is_clinical_contact("") is False
        assert is_clinical_contact(None) is False
        assert is_clinical_contact("   \n  ") is False

    def test_sms_only_dropped(self) -> None:
        text = (
            "10:32 - Surgery: [STAFF] (Receptionist Access Role) \n"
            "patient telephone number (9159.) - [phone]\n"
            "short message service text message sent to patient (xamii)\n\n"
            "Dear [PERSON],\n"
            "Please contact the surgery to book a routine appointment."
        )
        assert is_clinical_contact(text) is False

    def test_booking_confirmation_dropped(self) -> None:
        text = (
            "Dear [PERSON] appointment has been booked for "
            "06 Jan 2025 11:00 at Woodbrook Medical Centre."
        )
        assert is_clinical_contact(text) is False

    def test_appointment_reminder_dropped(self) -> None:
        text = (
            "Reminder of harold allwyn podiatry appointment on "
            "29 Oct 2024 15:50 at Loughborough hospital."
        )
        assert is_clinical_contact(text) is False

    def test_repeat_prescription_only_dropped(self) -> None:
        text = (
            "10:14 - Surgery: [STAFF] (Receptionist Access Role) \n"
            "(R) Indapamide 2.5mg tablets - 56 tablet - take one each morning\n"
            "(R) atorvastatin 20mg tablets - 56 tablet - take one at night\n"
            "ETP2 FP10: not yet printed - signed"
        )
        assert is_clinical_contact(text) is False

    def test_summary_care_record_only_dropped(self) -> None:
        text = (
            "12:50 - Surgery: [STAFF] (Receptionist Access Role) \n"
            "summary care record update - this patient's preference is for "
            "only core items to be included in their summary care record."
        )
        assert is_clinical_contact(text) is False

    def test_vaccine_invitation_dropped(self) -> None:
        text = (
            "13:26 - Surgery: [PERSON]  \n"
            "influenza vaccination invitation first short message service "
            "text message sent (ya16l) - added in bulk"
        )
        assert is_clinical_contact(text) is False

    def test_recall_reminder_dropped(self) -> None:
        text = (
            "Recall: blood test due (08 Jan 2025) repeat U&E in 3 months "
            "with urine ACR please."
        )
        assert is_clinical_contact(text) is False

    def test_auto_filed_unrelated_lab_dropped(self) -> None:
        # Routine HbA1c monitoring — no cancer-relevant test name.
        text = (
            "12:55 - Surgery: auto-filed  \n"
            "haemoglobin a1c level - ifcc standardised (xapbt) 41 mmol/mol "
            "[20 - 41] - please note changes in hba1c reporting from 27/09/21\n"
            "clinical information: reasons for request: rpt tests."
        )
        assert is_clinical_contact(text) is False

    def test_auto_filed_psa_kept(self) -> None:
        text = (
            "08:58 - Surgery: auto-filed  \n"
            "prostate-specific antigen level (xe25c) 12 ng/ml [0 - 6.5]\n"
            "outside reference range; PSA values are typically elevated "
            "following UTI..."
        )
        assert is_clinical_contact(text) is True

    def test_auto_filed_fit_kept(self) -> None:
        text = (
            "11:31 - Surgery: auto-filed  \n"
            "quantitative faecal immunochemical test (xaf0h) > 200 ug/g\n"
            "this is a UKAS accredited test, tested at Nottingham University "
            "Hospitals Trust. Refer via 2WW LGI pathway."
        )
        assert is_clinical_contact(text) is True

    def test_auto_filed_uss_kept(self) -> None:
        text = (
            "Surgery: [STAFF] (Admin/Clinical Support Access Role), entered by: [PERSON]\n"
            "auto-filed: USS abdomen: possible non-obstructing left renal stone "
            "(3.8mm), pancreas suggests fatty infiltration, multiple hepatic lesions."
        )
        assert is_clinical_contact(text) is True

    def test_pure_admin_secretary_dropped(self) -> None:
        text = "10:23 - Surgery: [STAFF] (Medical Secretary Access Role)"
        assert is_clinical_contact(text) is False

    def test_admin_with_clinical_history_kept(self) -> None:
        # Rare but real: GP writes their consultation note under a
        # secretary-tagged row (e.g. correcting a back-dated entry).
        text = (
            "Surgery: [STAFF] (Medical Secretary Access Role)\n"
            "history: F2F review re raised PSA. Discussed referral options."
        )
        assert is_clinical_contact(text) is True

    def test_f2f_consultation_kept(self) -> None:
        text = (
            "13:53 - GP Surgery: [STAFF] (Clinical Practitioner Access Role) \n"
            "136 / 89\n"
            "history: asked to come in due to concerns about bleeding from "
            "foreskin while on dapagliflozin. has been ongoing for a year."
        )
        assert is_clinical_contact(text) is True

    def test_telephone_consultation_kept(self) -> None:
        text = (
            "11:09 - Surgery: [STAFF] (Health Professional Access Role) \n"
            "history: teleconsult: spoke to pt confirmed DOB verified ID. "
            "Discussed her apixaban."
        )
        assert is_clinical_contact(text) is True

    def test_phlebotomy_kept(self) -> None:
        text = (
            "12:50 - Surgery: [STAFF] (Health Professional Access Role) \n"
            " phlebotomy service\n"
            "   0214 006 phlebotomy service\n"
            "      informed consent given for treatment   (xaxhk): yes\n"
            "      blood sample taken (cbs claim): yes"
        )
        assert is_clinical_contact(text) is True


# ---------------------------------------------------------------------------
# Contact-type classifier
# ---------------------------------------------------------------------------


class TestClassifyContactType:
    def test_f2f_review_classified_as_f2f(self) -> None:
        text = (
            "10:08 - GP Surgery: [STAFF] (Clinical Practitioner Access Role) \n"
            "history: F2F review. anterior neck mass noticed 3-4 months ago."
        )
        assert classify_contact_type(text) == "f2f"

    def test_telephone_consult_classified_as_telephone(self) -> None:
        text = (
            "13:13 - Surgery: [STAFF] (Clinical Practitioner Access Role) \n"
            "history: teleconsult ID confirmedx2. pharmacist suggested "
            "?visible haematuria - pink urine for quite some time."
        )
        assert classify_contact_type(text) == "telephone"

    def test_duty_call_classified_as_telephone(self) -> None:
        text = (
            "17:47 - Surgery: [STAFF] (Clinical Practitioner Access Role) \n"
            "history: duty call: from 111. problems with l leg since february."
        )
        assert classify_contact_type(text) == "telephone"

    def test_home_visit_classified_as_home_visit(self) -> None:
        text = (
            "16:12 - home of patient: [PERSON] (Clinical Practitioner Access Role) \n"
            "163 / 82\nhistory: home visit. introduced myself and gained consent."
        )
        assert classify_contact_type(text) == "home_visit"

    def test_specialist_clinic_classified_as_specialist_clinic(self) -> None:
        text = (
            "15:30 - clinic: [PERSON] (Clinical Practitioner Access Role) "
            "entered at: UHL Dermatology Service\n"
            " skin cancer follow up\n   skin cancer follow up\n"
            "      examination of lymph nodes: yes"
        )
        assert classify_contact_type(text) == "specialist_clinic"

    def test_phlebotomy_classified_as_phlebotomy(self) -> None:
        text = (
            "09:11 - Surgery: [STAFF] (Nurse Access Role) \n"
            " phlebotomy service\n"
            "   0214 006 phlebotomy service\n"
            "      blood sample taken (cbs claim): yes"
        )
        assert classify_contact_type(text) == "phlebotomy"

    def test_auto_filed_psa_classified_as_result_review(self) -> None:
        text = (
            "08:58 - Surgery: auto-filed  \n"
            "prostate-specific antigen level (xe25c) 12 ng/ml [0 - 6.5]"
        )
        assert classify_contact_type(text) == "result_review"

    def test_email_classified_as_email(self) -> None:
        text = (
            "14:02 - Surgery: [STAFF] (Receptionist Access Role) \n"
            "comment note (xaig6)\n"
            "e-mail sent to escalator33@hotmail.com via abtrace tool. "
            "Subject: medication monitoring blood test"
        )
        assert classify_contact_type(text) == "email"

    def test_unknown_text_classified_as_other(self) -> None:
        assert classify_contact_type("") == "other"
        assert classify_contact_type("17:08 - Surgery: [STAFF] (Clinical Practitioner Access Role)") == "other"


# ---------------------------------------------------------------------------
# Pre-filter pipeline (select_candidate_encounters)
# ---------------------------------------------------------------------------


class TestSelectCandidateEncounters:
    def test_pipeline_drops_admin_keeps_consultations(self) -> None:
        rows = [
            {
                "encounter_id": "e1",
                "date": "2025-01-06",
                "text": (
                    "11:11 - Surgery: [STAFF] (Clinical Practitioner Access Role) \n"
                    "problem: [d]change in bowel habit (r078.)\n"
                    "history: subjective: change in bowel habit for 6 months"
                ),
            },
            {
                "encounter_id": "e2",
                "date": "2025-01-06",
                "text": (
                    "Dear [PERSON] appointment has been booked for "
                    "14 Jan 2025 12:50 at Woodbrook Medical Centre."
                ),
            },
            {
                "encounter_id": "e3",
                "date": "2025-01-06",
                "text": (
                    "11:31 - Surgery: auto-filed  \n"
                    "quantitative faecal immunochemical test (xaf0h) > 200 ug/g"
                ),
            },
            {
                "encounter_id": "e4",
                "date": "2025-01-13",
                "text": "17:41 - Surgery: [STAFF] (Receptionist Access Role)",
            },
        ]
        candidates = select_candidate_encounters(rows)
        assert {c.encounter_id for c in candidates} == {"e1", "e3"}

    def test_pipeline_returns_chronological_order(self) -> None:
        rows = [
            {
                "encounter_id": "later",
                "date": "2025-01-23",
                "text": "history: F2F. discussed referral",
            },
            {
                "encounter_id": "earlier",
                "date": "2025-01-06",
                "text": "history: F2F review of bowel habit change",
            },
        ]
        candidates = select_candidate_encounters(rows)
        assert [c.encounter_id for c in candidates] == ["earlier", "later"]

    def test_pipeline_handles_none_rows(self) -> None:
        candidates = select_candidate_encounters([None, {"text": ""}])
        assert candidates == []


# ---------------------------------------------------------------------------
# build_user_message
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    def test_user_message_truncates_long_text(self) -> None:
        long = "a" * 2000
        cand = CandidateEncounter(
            encounter_id="e1",
            date="2025-01-01",
            text=long,
            contact_type="f2f",
        )
        msg = build_user_message(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-01",
            referral_date="2025-01-23",
            candidates=[cand],
            text_chars_per_candidate=300,
        )
        payload = json.loads(msg)
        assert payload["episode"]["cancer_type"] == "Colorectal"
        assert payload["episode"]["candidate_count"] == 1
        assert len(payload["candidates"][0]["text"]) == 300

    def test_user_message_handles_empty_candidate_list(self) -> None:
        msg = build_user_message(
            cancer_type=None,
            first_presentation_date=None,
            referral_date=None,
            candidates=[],
        )
        payload = json.loads(msg)
        assert payload["candidates"] == []
        assert payload["episode"]["candidate_count"] == 0


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------


def _make_candidates() -> list[CandidateEncounter]:
    return [
        CandidateEncounter(
            encounter_id="e1",
            date="2025-01-06",
            text="history: F2F. change in bowel habit. FIT requested.",
            contact_type="f2f",
        ),
        CandidateEncounter(
            encounter_id="e2",
            date="2025-01-14",
            text="phlebotomy service. blood sample taken.",
            contact_type="phlebotomy",
        ),
        CandidateEncounter(
            encounter_id="e3",
            date="2025-01-15",
            text="history: F2F follow-up. unrelated UTI workup.",
            contact_type="f2f",
        ),
    ]


class TestParseLlmResponse:
    def test_counts_recomputed_from_verdicts(self) -> None:
        # The LLM might disagree with itself; we always trust the verdicts.
        raw = {
            "encounters": [
                {"encounter_id": "e1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit change"},
                {"encounter_id": "e2", "date": "2025-01-14", "related": True,
                 "contact_type": "phlebotomy", "evidence": "FIT bloods"},
                {"encounter_id": "e3", "date": "2025-01-15", "related": False,
                 "contact_type": "f2f", "evidence": "UTI workup"},
            ],
            "factors": [
                {"factor": "consultations_to_discuss_test_results",
                 "evidence_encounter_ids": ["e2"],
                 "rationale": "FIT discussed"}
            ],
            "summary": {
                "consultations_n": 999,  # garbage — must be ignored
                "f2f_n": 999,
                "phone_n": 0,
                "nurse_n": 0,
                "email_n": 0,
                "specialist_clinic_n": 0,
                "home_visit_n": 0,
                "phlebotomy_n": 999,
                "result_review_n": 0,
                "unrelated_filtered_n": 0,
            },
        }
        result = parse_llm_response(raw, candidates=_make_candidates())
        # f2f=1 (e1) + phlebotomy=1 (e2)
        assert result.consultations_n == 2
        assert result.f2f_n == 1
        assert result.phlebotomy_n == 1
        assert result.unrelated_filtered_n == 1
        assert len(result.verdicts) == 3
        assert any(f.factor == "consultations_to_discuss_test_results" for f in result.factors)

    def test_no_consultations_forces_no_multiple_consultations_factor(self) -> None:
        raw = {
            "encounters": [
                {"encounter_id": "e1", "date": "2025-01-06", "related": False,
                 "contact_type": "f2f", "evidence": "unrelated"},
                {"encounter_id": "e2", "date": "2025-01-14", "related": False,
                 "contact_type": "phlebotomy", "evidence": "diabetes monitoring"},
            ],
            "factors": [],
        }
        result = parse_llm_response(raw, candidates=_make_candidates())
        assert result.consultations_n == 0
        assert result.unrelated_filtered_n == 2
        assert any(f.factor == "no_multiple_consultations" for f in result.factors)

    def test_invalid_factor_strings_silently_dropped(self) -> None:
        raw = {
            "encounters": [
                {"encounter_id": "e1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
                {"encounter_id": "e2", "date": "2025-01-14", "related": True,
                 "contact_type": "phlebotomy", "evidence": "FIT"},
            ],
            "factors": [
                {"factor": "made_up_factor", "evidence_encounter_ids": ["e1"]},
                {"factor": "consultations_to_discuss_test_results",
                 "evidence_encounter_ids": ["e2"]},
                {"factor": "inadequate_history_taken",  # human-review-only
                 "evidence_encounter_ids": ["e1"]},
            ],
        }
        result = parse_llm_response(raw, candidates=_make_candidates())
        kept = {f.factor for f in result.factors}
        assert "made_up_factor" not in kept
        # Human-review-only factors must not be auto-proposed even if
        # the LLM tries to.
        assert "inadequate_history_taken" not in kept
        assert "consultations_to_discuss_test_results" in kept

    def test_no_multiple_consultations_dropped_when_count_is_high(self) -> None:
        """Haiku occasionally proposes ``no_multiple_consultations``
        alongside real factors when the count is clearly >=2 — the
        parser must drop the contradictory factor so the dashboard
        doesn't show both."""
        raw = {
            "encounters": [
                {"encounter_id": "e1", "date": "2025-01-06", "related": True,
                 "contact_type": "f2f", "evidence": "bowel habit"},
                {"encounter_id": "e2", "date": "2025-01-14", "related": True,
                 "contact_type": "phlebotomy", "evidence": "FIT"},
            ],
            "factors": [
                {"factor": "different_initial_diagnosis",
                 "evidence_encounter_ids": ["e1"]},
                {"factor": "no_multiple_consultations",
                 "evidence_encounter_ids": []},
            ],
        }
        result = parse_llm_response(raw, candidates=_make_candidates())
        kept = {f.factor for f in result.factors}
        assert "no_multiple_consultations" not in kept
        assert "different_initial_diagnosis" in kept

    def test_invalid_contact_type_falls_back_to_pre_filter_tag(self) -> None:
        raw = {
            "encounters": [
                {"encounter_id": "e1", "date": "2025-01-06", "related": True,
                 "contact_type": "made_up_type", "evidence": "x"},
            ],
            "factors": [],
        }
        result = parse_llm_response(raw, candidates=_make_candidates())
        # e1 was tagged "f2f" by the pre-filter, so the bad LLM tag is ignored.
        assert result.f2f_n == 1
        assert result.consultations_n == 1


# ---------------------------------------------------------------------------
# classify_episode_consultations end-to-end (mocked LLM)
# ---------------------------------------------------------------------------


class TestClassifyEpisodeConsultations:
    def test_no_candidates_short_circuits_without_calling_llm(self) -> None:
        called: list[Any] = []

        def fake_caller(*args: Any, **kwargs: Any) -> dict[str, Any]:
            called.append(1)
            return {}

        result = classify_episode_consultations(
            cancer_type="Breast",
            first_presentation_date="2025-04-28",
            referral_date="2025-04-29",
            encounters=[
                {
                    "encounter_id": "noise1",
                    "date": "2025-04-26",
                    "text": "Dear [PERSON] appointment has been booked",
                },
                {
                    "encounter_id": "noise2",
                    "date": "2025-04-27",
                    "text": "(R) Letrozole 2.5mg tablets - 56 tablet",
                },
            ],
            llm_caller=fake_caller,
        )

        assert called == []
        assert result.consultations_n == 0
        assert result.factors[0].factor == "no_multiple_consultations"

    def test_happy_path_with_mocked_llm(self) -> None:
        captured: dict[str, Any] = {}

        def fake_caller(
            system_prompt: str,
            user_message: str,
            *,
            agent_task: str,
            patient_id: str,
        ) -> dict[str, Any]:
            captured["agent_task"] = agent_task
            captured["patient_id"] = patient_id
            captured["system_len"] = len(system_prompt)
            payload = json.loads(user_message)
            ids = [c["encounter_id"] for c in payload["candidates"]]
            return {
                "encounters": [
                    {"encounter_id": ids[0], "date": "2025-01-06",
                     "related": True, "contact_type": "f2f",
                     "evidence": "bowel habit change x6 months"},
                ],
                "factors": [
                    {"factor": "different_initial_diagnosis",
                     "evidence_encounter_ids": [ids[0]],
                     "rationale": "initially attributed to IBS"}
                ],
            }

        result = classify_episode_consultations(
            cancer_type="Colorectal",
            first_presentation_date="2025-01-06",
            referral_date="2025-01-23",
            patient_id="4469113522",
            encounters=[
                {
                    "encounter_id": "fp",
                    "date": "2025-01-06",
                    "text": (
                        "11:11 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
                        "history: F2F review. change in bowel habit x6 months."
                    ),
                },
            ],
            llm_caller=fake_caller,
        )

        assert captured["agent_task"] == "ncda_prior_consultations"
        assert captured["patient_id"] == "4469113522"
        assert captured["system_len"] > 500
        assert result.consultations_n == 1
        assert result.f2f_n == 1
        assert any(f.factor == "different_initial_diagnosis" for f in result.factors)

    def test_llm_error_falls_back_to_deterministic_count(self) -> None:
        def failing_caller(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"error": "Bedrock throttled"}

        result = classify_episode_consultations(
            cancer_type="Lymphoma",
            first_presentation_date="2024-12-04",
            referral_date="2024-12-05",
            patient_id="4200797127",
            encounters=[
                {
                    "encounter_id": "fp",
                    "date": "2024-12-04",
                    "text": (
                        "17:53 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
                        "history: F2F review. noticed glands have come up "
                        "this morning - left side of neck and right armpit."
                    ),
                },
            ],
            llm_caller=failing_caller,
        )
        # Deterministic fallback: classify_contact_type tagged this f2f
        # but ALL verdicts are marked related=False under fallback, so
        # consultations_n is the count of pre-filter-surviving rows
        # whose contact_type is in the counted set.
        assert result.consultations_n == 1
        assert "LLM error" in result.notes


# ---------------------------------------------------------------------------
# NCDA factor sets
# ---------------------------------------------------------------------------


class TestNcdaFactorSets:
    def test_no_overlap_between_tiers(self) -> None:
        auto = set(NCDA_FACTORS_AUTO_DETECTABLE)
        llm = set(NCDA_FACTORS_LLM_JUDGMENT)
        human = set(NCDA_FACTORS_HUMAN_REVIEW_ONLY)
        assert auto.isdisjoint(llm)
        assert auto.isdisjoint(human)
        assert llm.isdisjoint(human)

    def test_all_factors_have_a_label(self) -> None:
        all_factors = (
            set(NCDA_FACTORS_AUTO_DETECTABLE)
            | set(NCDA_FACTORS_LLM_JUDGMENT)
            | set(NCDA_FACTORS_HUMAN_REVIEW_ONLY)
        )
        assert all_factors == set(NCDA_FACTOR_LABELS.keys())
        assert len(all_factors) == 24


# ---------------------------------------------------------------------------
# empty_result_for_no_candidates
# ---------------------------------------------------------------------------


def test_empty_result_for_no_candidates_records_no_multiple_consultations() -> None:
    result = empty_result_for_no_candidates()
    assert result.consultations_n == 0
    assert result.factors[0].factor == "no_multiple_consultations"
