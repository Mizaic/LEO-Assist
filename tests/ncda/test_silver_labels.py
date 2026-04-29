"""Tests for Stage 3 silver-label generation."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.silver_labeller import (
    SilverLabel,
    deterministic_label,
    label_corpus,
    label_with_llm,
    labels_to_dicts,
)


def test_deterministic_label_picks_ftr_via_phrase():
    label = deterministic_label(
        patient_id="P1",
        encounter_id="E1",
        encounter_date="2024-01-15",
        text="Fast track referral for suspected breast cancer.",
        flags=None,
    )
    assert label.role == "ftr"
    assert label.outcome is None
    assert label.source == "deterministic"


def test_deterministic_label_picks_dx_with_excluded_outcome():
    label = deterministic_label(
        patient_id="P1",
        encounter_id="E1",
        encounter_date="2024-02-15",
        text="Discharged from 2WW, no malignancy on biopsy.",
        flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_excluded"


def test_deterministic_label_picks_dx_found_via_read_code():
    label = deterministic_label(
        patient_id="P1",
        encounter_id="E1",
        encounter_date="2024-02-15",
        text="(XE1vW) Malignant tumour of rectum",
        flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_embedded_problem_cancer_header_does_not_create_dx():
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-08-21",
        text=(
            "15:35 - Surgery: [STAFF] Problem: Metastasis to bone of unknown "
            "primary (Xa3AJ) Examination: Attended for XGEVA 120mg injection."
        ),
        flags=None,
    )

    assert label.role != "dx"


def test_choice_and_booking_admin_alone_does_not_create_ftr():
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-07-07",
        text=(
            "Referral for echocardiography (XaION) Choice and booking enhanced "
            "services administration (XaMJa)"
        ),
        flags=None,
    )

    assert label.role == "none"


def test_outbound_referral_code_alone_does_not_create_ftr():
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2024-08-22",
        text=(
            "Community Echocardiogram Referral Pathway Accessed. "
            "Referral to medical service (XaAcN). Outbound referral (XaY59)."
        ),
        flags=None,
    )

    assert label.role == "none"


def test_atrial_fibrillation_code_does_not_create_dx():
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-03-11",
        text="Atrial fibrillation (G5730) Bisoprolol medication review.",
        flags=None,
    )

    assert label.role == "none"


def test_generic_pet_code_does_not_create_dx_without_outcome_language():
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-08-08",
        text="Positron emission tomography (X70lS) (New Episode)",
        flags=None,
    )

    assert label.role == "none"


def test_auto_filed_lab_alone_is_excluded():
    """A bare auto-filed result (e.g. PSA, CXR) should still be silenced."""
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-04-10",
        text="Surgery: Auto-filed Entered at: UHL\nSerum vitamin D level (XE2e7) 45 nmol/L",
        flags=None,
    )

    assert label.role == "none"


def test_emis_major_new_episode_promotes_to_dx_cancer_found():
    """When the encounter contains EMIS 'Major: <cancer> ... (New Episode)'
    the labeller should classify it as dx/cancer_found regardless of any
    seen-in clinic Read codes that appear earlier in a composite encounter."""
    text = (
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "2WW\n"
        "Seen in 2WW Clinic?: Seen in fast track suspected skin cancer clinic (XaPyd)\n"
        "Histology: pT1b\n"
        "Major: Malignant melanoma (Xa99S) - stage pT1b - Right upper back (New Episode)\n"
        "Excision of skin lesion (Xa8Pv)\n"
    )
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-05-12",
        text=text,
        flags=None,
    )

    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_auto_filed_does_not_silence_diagnosis_block():
    """Composite encounter containing both an auto-filed lab AND a real
    diagnosis/treatment block should not be wholesale excluded."""
    text = (
        "Letter\nDermatology to GP\n"
        "Surgery: Auto-filed Entered at: UHL Dermatology Service\n"
        "Serum vitamin D level (XE2e7) 45 nmol/L\n"
        "Histology confirms malignant melanoma in situ\n"
        "Wide local excision performed.  Excision of skin lesion (Xa8Pv).\n"
    )
    label = deterministic_label(
        patient_id="p",
        encounter_id="e",
        encounter_date="2025-05-12",
        text=text,
        flags=None,
    )

    assert label.role != "none"


def test_deterministic_label_falls_back_to_none_for_admin_text():
    label = deterministic_label(
        patient_id="P1",
        encounter_id="E1",
        encounter_date=None,
        text="Patient called regarding letter from clinic.",
        flags=None,
    )
    assert label.role == "none"
    assert label.outcome is None
    assert label.confidence < 0.7


def test_label_with_llm_respects_callback_response():
    def fake_llm(text: str, flags):
        return {
            "role": "ftr",
            "outcome": None,
            "confidence": 0.92,
            "rationale": "Matched 'Fast track referral'",
            "supporting_quote": "Fast track referral",
            "site_hint": "skin",
        }

    label = label_with_llm(
        patient_id="P1",
        encounter_id="E1",
        encounter_date="2024-01-15",
        text="Fast track referral for suspected skin cancer.",
        flags=None,
        llm=fake_llm,
    )
    assert label.role == "ftr"
    assert label.confidence == 0.92
    assert label.source == "llm"
    assert label.site_hint == "skin"


def test_label_with_llm_strips_invalid_role():
    def bad_llm(text: str, flags):
        return {"role": "WHATEVER", "confidence": 0.9}

    label = label_with_llm(
        patient_id="P1",
        encounter_id="E1",
        encounter_date=None,
        text="text",
        flags=None,
        llm=bad_llm,
    )
    assert label.role == "none"


def test_label_with_llm_drops_outcome_when_role_not_dx():
    def llm(text: str, flags):
        return {
            "role": "ftr",
            "outcome": "cancer_found",
            "confidence": 0.8,
            "rationale": "x",
            "supporting_quote": "y",
        }

    label = label_with_llm(
        patient_id="P1",
        encounter_id="E1",
        encounter_date=None,
        text="text",
        flags=None,
        llm=llm,
    )
    assert label.role == "ftr"
    assert label.outcome is None


def test_label_corpus_falls_back_to_deterministic_on_llm_error():
    def broken_llm(text: str, flags):
        raise RuntimeError("API key invalid")

    rows = [
        {
            "patient_id": "P1",
            "encounter_id": "E1",
            "encounter_date": "2024-01-15",
            "text": "Fast track referral",
            "flags": None,
        }
    ]
    labels = label_corpus(rows, llm=broken_llm)
    assert len(labels) == 1
    assert labels[0].source == "deterministic"


def test_label_corpus_with_no_llm_uses_deterministic():
    rows = [
        {
            "patient_id": "P1",
            "encounter_id": "E1",
            "encounter_date": "2024-01-15",
            "text": "Fast track referral for suspected breast cancer.",
            "flags": None,
        },
        {
            "patient_id": "P1",
            "encounter_id": "E2",
            "encounter_date": "2024-02-10",
            "text": "Decapeptyl 1st injection.",
            "flags": None,
        },
    ]
    labels = label_corpus(rows, llm=None)
    assert {label.role for label in labels} == {"ftr", "treatment"}
    assert all(label.source == "deterministic" for label in labels)


def test_labels_to_dicts_preserves_schema():
    label = SilverLabel(
        patient_id="P1",
        encounter_id="E1",
        encounter_date="2024-01-15",
        role="ftr",
        outcome=None,
        confidence=0.7,
        rationale="x",
        supporting_quote="y",
        site_hint=None,
        source="deterministic",
    )
    rows = labels_to_dicts([label])
    assert rows[0]["role"] == "ftr"
    assert rows[0]["outcome"] is None
    assert rows[0]["source"] == "deterministic"


def test_silver_outcome_only_when_role_is_dx():
    rows = [
        {
            "patient_id": "P1",
            "encounter_id": "E1",
            "encounter_date": "2024-01-15",
            "text": "Started Tamoxifen",
            "flags": None,
        }
    ]
    labels = label_corpus(rows, llm=None)
    for label in labels:
        if label.role != "dx":
            assert label.outcome is None
        else:
            assert label.outcome in ("cancer_found", "cancer_excluded")
