"""Tests for prostate episode membership noise filter (runner)."""

from __future__ import annotations

from datetime import date

import pytest

from services.analysis_worker.app.episode_detector_v2.runner import (
    _drop_prostate_low_value_encounters,
    _prostate_encounter_is_membership_noise,
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
