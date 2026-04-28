"""Tests for Stage 1 deterministic audit rules."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.audit_rules import (
    MilestonedEncounter,
    extract_read_codes,
    find_duplicate_roles,
    find_out_of_sequence,
    find_role_mismatches,
    parse_entry_date,
    read_codes_support_role,
    text_supports_role,
)


def _enc(
    *,
    patient_id="P1",
    episode_id="E1",
    encounter_id="ENC1",
    milestone_type="referral",
    encounter_date="2024-01-15",
    text="",
    flags=None,
) -> MilestonedEncounter:
    return MilestonedEncounter(
        patient_id=patient_id,
        episode_id=episode_id,
        encounter_id=encounter_id,
        milestone_type=milestone_type,
        encounter_date=encounter_date,
        text=text,
        flags=flags,
    )


def test_extract_read_codes_finds_alphanumeric_tokens():
    text = "GP referred via 2WW (XaMeA) to dermatology. Note (Pharmacist) seen."
    codes = extract_read_codes(text)
    assert "XaMeA" in codes
    assert "Pharmacist" in codes


def test_extract_read_codes_handles_empty_text():
    assert extract_read_codes("") == []
    assert extract_read_codes(None) == []


def test_text_supports_ftr_role_via_phrase():
    assert text_supports_role("Patient referred under 2WW pathway.", "ftr")


def test_text_supports_ftr_role_with_fast_track_phrase():
    assert text_supports_role("Fast track referral for suspected cancer.", "ftr")


def test_text_supports_dx_excluded_phrase():
    assert text_supports_role("Discharged from 2WW pathway, benign findings.", "dx")
    assert text_supports_role("No malignancy detected on biopsy.", "dx")


def test_text_supports_treatment_phrase():
    assert text_supports_role("First cycle chemotherapy administered.", "treatment")


def test_read_codes_support_role_via_curated_lookup():
    text = "GP referred via fast-track pathway (XaMeA) for skin lesion."
    assert read_codes_support_role(text, "ftr")


def test_read_codes_support_role_drug_token():
    text = "Started (DECAPEPTYL) injection."
    assert read_codes_support_role(text, "treatment")


def test_read_codes_ignore_junk_tokens():
    text = "Letter (Requested) from clinic."
    assert not read_codes_support_role(text, "ftr")


def test_role_mismatch_flagged_when_no_evidence():
    enc = _enc(milestone_type="referral", text="Telephone consultation about back pain.")
    findings = find_role_mismatches([enc])
    assert len(findings) == 1
    assert findings[0].finding_type == "role_mismatch"
    assert findings[0].severity == "medium"


def test_role_mismatch_clears_when_phrase_present():
    enc = _enc(
        milestone_type="referral", text="Patient referred via 2WW for breast lump."
    )
    assert find_role_mismatches([enc]) == []


def test_role_mismatch_clears_when_curated_read_code_present():
    enc = _enc(milestone_type="referral", text="Sent referral letter (XaMJa).")
    assert find_role_mismatches([enc]) == []


def test_out_of_sequence_flags_dx_before_ftr():
    ftr = _enc(
        encounter_id="ENC1",
        milestone_type="referral",
        encounter_date="2024-05-10",
        text="(XaMeA) 2WW referral",
    )
    dx = _enc(
        encounter_id="ENC2",
        milestone_type="diagnosis_confirmed",
        encounter_date="2024-04-01",
        text="(XE1vW) malignant rectal tumour",
    )
    findings = find_out_of_sequence([ftr, dx])
    assert findings, "Expected an out_of_sequence finding"
    assert any(f.severity == "high" for f in findings)


def test_out_of_sequence_clears_for_proper_ordering():
    ftr = _enc(encounter_id="A", milestone_type="referral", encounter_date="2024-01-15")
    seen = _enc(encounter_id="B", milestone_type="first_seen", encounter_date="2024-01-25")
    dx = _enc(
        encounter_id="C", milestone_type="diagnosis_confirmed", encounter_date="2024-02-15"
    )
    treatment = _enc(
        encounter_id="D",
        milestone_type="treatment_started",
        encounter_date="2024-03-01",
    )
    assert find_out_of_sequence([ftr, seen, dx, treatment]) == []


def test_duplicate_roles_flagged():
    a = _enc(encounter_id="A", milestone_type="referral_sent", encounter_date="2024-01-01")
    b = _enc(encounter_id="B", milestone_type="referral", encounter_date="2024-01-02")
    findings = find_duplicate_roles([a, b])
    assert len(findings) == 1
    assert findings[0].finding_type == "multiple_anchors_per_role"
    assert findings[0].suggested_role == "ftr"


def test_duplicate_roles_silent_for_distinct_roles():
    a = _enc(encounter_id="A", milestone_type="referral", encounter_date="2024-01-01")
    b = _enc(encounter_id="B", milestone_type="first_seen", encounter_date="2024-01-15")
    assert find_duplicate_roles([a, b]) == []


def test_parse_entry_date_extracts_back_dated_value():
    flags = "Linked to Appointment | back-dated entry on: 15 Jan 2024"
    assert parse_entry_date(flags) == "2024-01-15"


def test_parse_entry_date_handles_missing_back_date():
    assert parse_entry_date(None) is None
    assert parse_entry_date("Face to face") is None
