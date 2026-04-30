"""Tests for the encounter pre-classifier."""

import pytest

from libs.cohort_annotation.classifier import classify
from libs.cohort_annotation.state import EncounterClass


# ---------------------------------------------------------------------------
# EMPTY cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "",
    "   ",
    "Surgery: [STAFF] (Pharmacist)",
    "10:43 - Surgery: [STAFF] (Receptionist Access Role)",
    "10:43 - Surgery: [STAFF] (Nurse Access Role)",
    "Surgery: [STAFF] (Admin/Clinical Support Access Role)",
    "Automatically updated from PAS interface: Unknown Staff Member  Entered at: University Hospitals",
    "Summary Care Record Update - This patient's preference is for only core items",
    "Dear [PERSON] appointment has been booked for 18 Feb 2025 11:40 at Woodbrook Medical Centre.",
    "Seen in clinic (A&E:XaBKC)",
])
def test_empty_encounters(text):
    assert classify(text) == EncounterClass.EMPTY


# ---------------------------------------------------------------------------
# LETTER cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Dermatology outpatient letter to Dr Smith, Acacia Surgery.\nPatient seen in 2WW skin clinic.",
    "clinic letter from Mr Jones, Oncology Department",
    "Discharge summary from Ward 7B.\nDiagnosis: carcinoma of breast.",
    "letter to GP from Gastroenterology Service",
])
def test_letter_encounters(text):
    result = classify(text)
    assert result == EncounterClass.LETTER, f"Expected LETTER, got {result} for: {text[:60]}"


# ---------------------------------------------------------------------------
# STRUCTURED cases
# ---------------------------------------------------------------------------

STRUCTURED_TEXT = (
    "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range\n"
    "Haemoglobin estimation (423..) 138 g/L [120 - 160]\n"
    "Serum sodium (XE2q9) 140 mmol/L\n"
    "Pathology Request (Complete): HbA1c (Requested), Full Blood Count (Requested)"
)


def test_structured_lab_block():
    result = classify(STRUCTURED_TEXT)
    assert result in (EncounterClass.STRUCTURED, EncounterClass.MIXED)


# ---------------------------------------------------------------------------
# NARRATIVE cases
# ---------------------------------------------------------------------------

NARRATIVE_TEXT = (
    "History: F2F review with patient.\n"
    "Presenting with a 3-week history of intermittent rectal bleeding.\n"
    "Patient is a 65-year-old male, non-smoker.\n"
    "Examination: abdomen soft, non-tender, no organomegaly.\n"
    "Plan: refer urgently for 2WW lower GI pathway."
)


def test_narrative_encounter():
    result = classify(NARRATIVE_TEXT)
    assert result in (EncounterClass.NARRATIVE, EncounterClass.MIXED)


# ---------------------------------------------------------------------------
# MIXED cases
# ---------------------------------------------------------------------------

MIXED_TEXT = (
    "128 / 88\n"
    "Body mass index - observation (22K..) 26.03 Kg/m\n"
    "History: F2F consult for annual LTC review.\n"
    "Patient reports occasional headaches.\n"
    "HbA1c (Requested), Full Blood Count (Requested)\n"
)


def test_mixed_encounter():
    result = classify(MIXED_TEXT)
    assert result in (EncounterClass.MIXED, EncounterClass.STRUCTURED, EncounterClass.NARRATIVE)


# ---------------------------------------------------------------------------
# Non-empty short clinical content is NOT empty
# ---------------------------------------------------------------------------

def test_short_clinical_is_not_empty():
    text = "BP 142/88. Advised to increase antihypertensive dose."
    assert classify(text) != EncounterClass.EMPTY
