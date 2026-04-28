"""Tests for prostate episode membership noise filter (runner)."""

from __future__ import annotations

from datetime import date

import pytest

from services.analysis_worker.app.episode_detector_v2.runner import (
    _drop_prostate_low_value_encounters,
    _prostate_encounter_is_membership_noise,
    _truncate_prostate_after_treatment_start,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def test_keeps_thin_oncology_routing_stub_for_curator_alignment():
    t = "Surgery: [STAFF] (Receptionist Access Role)  Oncology to Woodbrook Medical Centre"
    assert not _prostate_encounter_is_membership_noise(t.lower())


def test_noise_minor_injuries_even_if_prostate_in_history():
    t = "Minor Injuries  History:  prostate cancer  hip pain"
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_case_management_mdt_only_when_weak_significant_event():
    t = "Case Management  MDT  Reason for discussion: significant event  LUTS male"
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_keeps_case_management_mdt_when_staging_named():
    t = (
        "Case Management  MDT  Issues identified:  delay 2ww  "
        "T4N1M1 ca prostate  agreed actions: documentation"
    )
    assert not _prostate_encounter_is_membership_noise(t.lower())


def test_noise_continence_supplies_without_pathway_in_text():
    t = (
        "LLR Continence Service  triage  supplies  "
        "past medical history osteoarthritis only"
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_keeps_continence_when_post_prostatectomy_urology_referral():
    t = (
        "LLR Continence Service  referral from urology  "
        "pad provision following prostatectomy"
    )
    assert not _prostate_encounter_is_membership_noise(t.lower())


def test_noise_keeps_catheter_bypassing():
    t = "Continence Service  bypassing urethral catheter  poor drainage"
    assert not _prostate_encounter_is_membership_noise(t.lower())


def test_drop_never_removes_anchor():
    timeline = [
        TimelineEvent(
            encounter_id="a",
            occurred_on=date(2025, 1, 1),
            event_kind="encounter",
            text_snippet="NHS Health Check programme routine review",
        ),
        TimelineEvent(
            encounter_id="b",
            occurred_on=date(2025, 1, 2),
            event_kind="encounter",
            text_snippet="NHS Health Check programme routine review",
        ),
    ]
    out = _drop_prostate_low_value_encounters(
        ["a", "b"],
        timeline,
        anchor_event_id="b",
    )
    assert out == ["b"]


@pytest.mark.parametrize(
    "snippet",
    [
        "behind on Accurx messages",
        "NHS Health Check programme",
        "bleeding from foreskin while on dapagliflozin",
    ],
)
def test_noise_primary_care_or_admin(snippet: str):
    assert _prostate_encounter_is_membership_noise(snippet.lower())


def test_noise_clinical_supervision_patient_absent():
    t = "Clinical Supervision  Discussed with supervisor: Yes  Patient present: No (Y0428)  Notes: repeat PSA"
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_auto_filed_ue_without_2ww_tag():
    t = (
        "Surgery: Auto-filed  Serum creatinine level 84 umol/L  "
        "eGFR using creatinine  Urea and electrolytes report normal"
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_keeps_auto_filed_ue_when_2ww_bloods_requested():
    t = (
        "Surgery: Auto-filed  Reasons for Request: 2ww bloods.  "
        "Serum urea level (XM0lt) 5.8 mmol/L"
    )
    assert not _prostate_encounter_is_membership_noise(t.lower())


def test_noise_chest_pain_spect_coronary_even_if_prostate_history():
    t = (
        "Problem: Malignant tumour of prostate  "
        "Chest pain  SPECT CT  calcified coronary  prostate cancer staging"
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_copd_review_with_prostate_history_only():
    t = (
        "Problem: COPD exacerbation. Past Medical History includes emphysema, "
        "COPD, and prostate cancer. Currently receiving hormone injections "
        "every 3 months for prostate cancer. Plan: FBC, U&E and ECG for "
        "possible heart failure."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_copd_review_recent_prostate_diagnosis_reference():
    t = (
        "Problem: Emphysematous. History: Attended for COPD review. "
        "Informed me feels okay in regards to respiratory symptoms. "
        "Has recently been diagnosed with prostate cancer."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_af_heart_failure_review_mentions_adt_and_radiotherapy():
    t = (
        "Problem: Atrial fibrillation. Problem: Heart failure. Presenting for "
        "review of blood test results following initiation of a diuretic. "
        "Reports history of prostate cancer, receiving ADT, and upcoming "
        "radiotherapy."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_mechanical_back_pain_before_radiotherapy_planning():
    t = (
        "AI consultation summary: right-sided lower back pain. Assessment: "
        "mechanical lower back pain, likely musculoskeletal in origin. "
        "Past Medical History: prostate cancer, awaiting commencement of "
        "radiotherapy."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_generic_pathology_panel_without_prostate_hook():
    t = (
        "Pathology Request (Complete): Bone Profile, Coagulation screen, "
        "Full Blood Count, Liver Function Test, NT - Pro BNP, "
        "Thyroid Stimulating Hormone, Urea & electrolytes"
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_bare_psa_request_without_pathway_hook():
    t = "Pathology Request (Complete): Prostate Specific Antigen (Requested)"
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_keeps_urology_biopsy_admin_and_actual_hormone_injection():
    biopsy = (
        "Email from Urology, Patient is listed tomorrow for a template biopsy. "
        "Once this has been done, we will receive the discharge letter."
    )
    injection = (
        "Problem: Malignant tumour of prostate. Decapeptyl SR 11.25mg "
        "GNRH given. Given under PSD."
    )
    assert not _prostate_encounter_is_membership_noise(biopsy.lower())
    assert not _prostate_encounter_is_membership_noise(injection.lower())


def test_noise_thin_urology_routing_stub():
    t = "Surgery: [STAFF] (Receptionist Access Role) Urology to Woodbrook Medical Centre"
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_msk_back_pain_with_no_urinary_symptoms():
    t = (
        "lower back pain - started 5 days ago. no urinary sx - no prostatism, "
        "no weight loss, no haematuria. Plan: MSK lower back issues most likely; "
        "attend prostate biopsy to rule out any relation."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_ltc_psa_monitoring_without_pathway_action():
    t = (
        "LTC Review Initial Review & Tests. LLR PSA Monitoring. "
        "Prostate-specific antigen monitoring (CBS claim). "
        "Blood test type: Routine."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_nss_other_referral_from_prostate_episode():
    t = (
        "Fast track referral for suspected cancer due to non-site-specific "
        "symptoms. Patient awaiting OPD appt.: Yes 2WW non site specific. "
        "NSS pathway CT noted."
    )
    assert _prostate_encounter_is_membership_noise(t.lower())


def test_noise_transferring_care_safely_admin_stub():
    for t in (
        "Transferring care safely referral sent today. NHSmail to Unknown.",
        "Trasferring care safely referral sent today. NHSmail to Unknown.",
    ):
        assert _prostate_encounter_is_membership_noise(t.lower())


def test_truncates_prostate_episode_after_first_actual_treatment_start():
    timeline = [
        TimelineEvent(
            encounter_id="dx",
            occurred_on=date(2024, 10, 8),
            event_kind="encounter",
            text_snippet=(
                "Major: Malignant tumour of prostate - Gleason 3+4=7; "
                "T3aN0 (New Episode)"
            ),
        ),
        TimelineEvent(
            encounter_id="planned",
            occurred_on=date(2024, 12, 17),
            event_kind="encounter",
            text_snippet=(
                "Problem: Malignant tumour of prostate. request for PSD. "
                "Plan: to start the injections half way into the Bicalutamide course."
            ),
        ),
        TimelineEvent(
            encounter_id="treatment",
            occurred_on=date(2024, 12, 27),
            event_kind="encounter",
            text_snippet=(
                "Problem: Malignant tumour of prostate. Attended for 1st "
                "Decapeptyl injection. GNRH given. Given under PSD."
            ),
        ),
        TimelineEvent(
            encounter_id="later",
            occurred_on=date(2025, 3, 5),
            event_kind="encounter",
            text_snippet="Attended for Decapeptyl injection. GNRH given.",
        ),
    ]

    out = _truncate_prostate_after_treatment_start(
        ["dx", "planned", "treatment", "later"],
        timeline,
    )

    assert out == ["dx", "planned", "treatment"]
