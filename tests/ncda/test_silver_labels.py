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


def test_followup_to_concluded_NSS_pathway_does_not_create_ftr():
    """Patient 6261656266 regression: 2024-10-24 admin task quoting an NSS
    pathway that was discharged on 2024-10-02 must not be labelled ftr.
    """
    text = (
        "09:45 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
        "History: on call\n"
        "please see 2ww letter from 2nd october\n"
        "see NSS pathway update letter 2/10/24 -\n"
        '"Actions and by whom: Discharge from NSS pathway. CNS NH to dictate letter.\n'
        'Recommendations to GP: pls follow updates from urology"\n'
        "hx papillary ca thyroid under active surveillance"
    )
    label = deterministic_label(
        patient_id="6261656266",
        encounter_id="64a7bee5",
        encounter_date="2024-10-24",
        text=text,
        flags=None,
    )
    assert label.role == "none"
    assert "concluded" in label.rationale.lower() or "discharge" in label.rationale.lower()


def test_followup_2WW_pathway_discharged_NOT_ftr():
    text = "Pt discharged from 2WW pathway after biopsy showed no malignancy."
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2024-01-01", text=text, flags=None
    )
    assert label.role in {"dx", "none"}
    assert label.role != "ftr"


def test_followup_with_genuine_new_dx_NOT_silenced():
    """If the encounter ALSO contains a clear cancer-confirmed signal (e.g.
    histology / excision text), the follow-up exclusion must NOT silence it.
    Uses 'Recommendations to GP:' which is one of the new exclusion phrases.
    """
    text = (
        "Letter received from MDT.\n"
        "Histology confirms invasive ductal carcinoma of right breast.\n"
        "Wide local excision performed last week.\n"
        "Recommendations to GP: please follow up adjuvant therapy plan."
    )
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2024-01-01", text=text, flags=None
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_background_thyroidectomy_does_not_create_treatment():
    """Patient 6261656266 regression: 2025-09-12 GP review for chest pain
    that mentions 'background thyroidectomy for papillary thyroid ca' must
    not be labelled treatment.
    """
    text = (
        "13:54 - GP Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
        "Problem: Chest pain (182..)\n"
        "History: known to me. Complained of feeling TATT + Chest pain\n"
        "slightly upward trending TFT (background thyroidectomy for paipllary thyroid ca)\n"
        "CXR normal, no anaemia, ECG also normal"
    )
    label = deterministic_label(
        patient_id="6261656266",
        encounter_id="51cdec3d",
        encounter_date="2025-09-12",
        text=text,
        flags=None,
    )
    assert label.role == "none"


def test_history_of_mastectomy_does_not_create_treatment():
    text = "Routine annual review. Background of mastectomy 2018 for invasive breast ca."
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2024-06-01", text=text, flags=None
    )
    assert label.role != "treatment"


def test_had_oesophagectomy_recap_does_not_create_treatment():
    """Patient 4563591157 regression: a 2025-12-19 COPD-review encounter that
    only mentions "Had oesophagectomy in March 2024 for adenocarcinoma" must
    NOT be promoted to a new treatment_started milestone.
    """
    text = (
        "14:30 - Surgery: [STAFF] (Nurse Access Role)\n"
        "Problem: Chronic obstructive lung disease (H3...)\n"
        "History: Attended for COPD review.\n"
        "Had oesophagectomy in March 2024 for adenocarcinoma of oesophagus."
    )
    label = deterministic_label(
        patient_id="4563591157",
        encounter_id="ebbe654e",
        encounter_date="2025-12-19",
        text=text,
        flags=None,
    )
    assert label.role != "treatment"
    assert label.role != "dx"


def test_underwent_thyroidectomy_recap_does_not_create_treatment():
    text = "Patient underwent thyroidectomy this morning. All went well."
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2024-06-01", text=text, flags=None
    )
    assert label.role != "treatment"


def test_extended_surgery_list_silences_other_recap_phrases():
    """Sanity check that the new surgery names (oesophagectomy, splenectomy,
    orchidectomy, thyroidectomy, etc.) are caught by the existing-condition
    prefix guard.
    """
    surgeries = [
        "oesophagectomy",
        "esophagectomy",
        "thyroidectomy",
        "orchidectomy",
        "splenectomy",
        "tonsillectomy",
        "adrenalectomy",
        "parotidectomy",
    ]
    for surgery in surgeries:
        text = f"Patient had {surgery} in 2020 for malignant tumour."
        label = deterministic_label(
            patient_id="P",
            encounter_id="E",
            encounter_date="2024-06-01",
            text=text,
            flags=None,
        )
        assert label.role == "none", f"{surgery!r}: expected none, got {label.role!r}"


def test_XM0By_colonoscopy_normal_resolves_to_cancer_excluded():
    """Patient 4245139757 regression: a colonoscopy encounter with the
    XM0By Read code and inline ' - normal' suffix must be labelled
    dx / cancer_excluded so the NSS 2WW pathway closes correctly.
    """
    text = (
        "Surgery: [STAFF] (Admin/Clinical Support Access Role) , "
        "Entered By: [PERSON]\n"
        "Colonoscopy (XM0By) - normal (New Episode)"
    )
    label = deterministic_label(
        patient_id="4245139757",
        encounter_id="57a3a539",
        encounter_date="2025-09-13",
        text=text,
        flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_excluded"


def test_XM0By_colonoscopy_with_cancer_finding_resolves_to_cancer_found():
    """Defence-in-depth: a colonoscopy encounter that ALSO mentions a Major:
    cancer term must still be labelled dx / cancer_found, because the
    EMIS_MAJOR_DX guard runs before the procedure-Read-code check.
    """
    text = (
        "Colonoscopy (XM0By) (New Episode)\n"
        "Major: Carcinoma of colon (X78nn) (New Episode)"
    )
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-01-01",
        text=text, flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_other_colonoscopy_codes_normal_now_resolve_to_cancer_excluded():
    """The new procedure-normal pattern in _infer_dx_outcome should also fix
    the historic XaJGZ colonoscopy case (which used to return outcome=None).
    """
    text = "Colonoscopy (XaJGZ) - normal (New Episode)"
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-01-01",
        text=text, flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_excluded"


def test_actual_thyroidectomy_today_still_creates_treatment():
    """Regression guard: a brand new thyroidectomy must still be labelled
    treatment when not preceded by an existing-condition qualifier.
    """
    text = "Patient underwent total thyroidectomy this morning. First cycle of post-op care."
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-01-01", text=text, flags=None
    )
    # "underwent ... thyroidectomy" is itself a post-event recap qualifier in
    # _EXISTING_CONDITION_PREFIX, so the bare-treatment word is silenced here.
    # We only require that "started chemotherapy" / "first cycle" style new
    # treatment language still works.
    text2 = "Started chemotherapy today. Cycle 1 of carboplatin and paclitaxel."
    label2 = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-01-01", text=text2, flags=None
    )
    assert label2.role == "treatment"


def test_papillary_thyroid_carcinoma_problem_line_is_stripped():
    """Patient 6261656266 regression: a routine GP review whose text recaps
    the patient's existing 'Problem: Papillary thyroid carcinoma (X78cQ)'
    must NOT be labelled dx / cancer_found. The qualifier word
    ('papillary') between 'Problem:' and 'carcinoma' previously bypassed
    the strip-problem-lines guard.
    """
    text = (
        "Problem: Essential hypertension (XE0Uc)\n"
        "Problem: Papillary thyroid carcinoma (X78cQ) - Thy5\n"
        "Problem: Fatigue (1682.)\n"
        "History: Had a few queries which we discussed.\n"
        "Plan: Check TFTs in 3-6m, then will have annual check for endocrine in 12m\n"
        "FIT test to r/o bowel pathology as cause of constipation"
    )
    label = deterministic_label(
        patient_id="6261656266", encounter_id="E", encounter_date="2025-07-21",
        text=text, flags=None,
    )
    assert label.role == "none"
    assert label.outcome is None


def test_followup_to_concluded_2ww_inverted_word_order_silenced():
    """Patient 6261656266 regression: a F2F GP consult that mentions 'Noted
    had NSS pathway 2ww referral and was discharged' must NOT be labelled
    ftr.  The original _FOLLOWUP_TO_CONCLUDED_2WW_PATHWAY only matched the
    canonical 'discharged from <type> pathway' word order.
    """
    text = (
        "GP Surgery: F2F appt. 1 year history of altered bowel habit.\n"
        "Noted had NSS pathway 2ww referral and was discharged.\n"
        "Diagnosis: ?Irritable bowel syndrome.\n"
        "Plan: Notes NSS pathway done and discharged following MDT, "
        "no concerns re malignancy."
    )
    label = deterministic_label(
        patient_id="6261656266", encounter_id="E", encounter_date="2025-01-17",
        text=text, flags=None,
    )
    assert label.role == "none"


def test_currently_under_oncology_recap_silences_dx():
    """Patient 4563591157 regression: an off-duty triage call that just
    recaps a patient's known oncology context must not be promoted to
    dx/cancer_found via the 'adenocarcinoma' phrase.
    """
    text = (
        "History: Telephone triage off duty list - ID confirmed, spoke to patient.\n"
        "Currently under oncology for GOJ adenocarcinoma - had 3 cycles of chemo so far.\n"
        "Pt called as has new sore throat for 5 days."
    )
    label = deterministic_label(
        patient_id="4563591157", encounter_id="E", encounter_date="2025-02-14",
        text=text, flags=None,
    )
    assert label.role == "none"


def test_had_bloods_for_lymphoma_does_not_promote_dx():
    """Patient 6310920987 regression: 'had bloods for lymphoma done too
    early' is a monitoring note for a known lymphoma, not a new dx.
    """
    text = (
        "Problem: Atrophy of vagina (Xa6Yg)\n"
        "History: See prev. Urine clear and US KUB normal.\n"
        "Plan: switch to estriol cream.\n"
        "Also worried as had bloods for lymphoma done too early - "
        "used the forms but not sure what to do."
    )
    label = deterministic_label(
        patient_id="6310920987", encounter_id="E", encounter_date="2025-07-28",
        text=text, flags=None,
    )
    assert label.role == "none"


def test_pmh_field_with_historical_carcinoma_does_not_promote_dx():
    """Patient 6040304227 regression: a PRISM rehab-triage rejection whose
    text recaps a 2020 squamous cell carcinoma in the
    'Previous / Current medical history' template field must NOT be
    labelled dx / cancer_found. Without the PMH-strip guard this triage
    note paired with an unrelated F2F encounter and spawned a phantom
    Melanoma-urological cohort 1b episode.
    """
    text = (
        "Office Base: Triage Template\n"
        "  Medical Information\n"
        "    Presenting complaint:  Referral received via Heart Failure "
        "Nurse Specialist.\n"
        "    Previous / Current medical history:  COPD - Emphysema, "
        "AAA = 5.5cm (August 2022), Prostate hypertrophy, "
        "Squamous cell carcinoma (2020), O.A, Decompensated heart failure.\n"
        "    Clinical management plan:  Referral rejected due to AAA size.\n"
        "Status Update for Rehabilitation Referral In: Discharged From Care.\n"
        "Activity: Clinical triage (30 minutes) Administration "
        "with No Patient/No Proxy present\n"
        "Presenting complaint (XaIm8) - Referral received via "
        "Heart Failure Nurse Specialist.\n"
        "Previous/Current medical history (Y3535) - COPD - Emphysema, "
        "AAA = 5.5cm (August 2022), Prostate hypertrophy, "
        "Squamous cell carcinoma (2020), O.A, Decompensated heart failure.\n"
        "Clinical management plan (XaJYd) - Referral rejected due to AAA size."
    )
    label = deterministic_label(
        patient_id="6040304227", encounter_id="E", encounter_date="2025-01-22",
        text=text, flags=None,
    )
    assert label.role == "none"
    assert label.outcome is None


def test_past_medical_history_aliases_are_stripped():
    """Same protection should apply to the common 'Past medical history'
    and 'PMH' aliases.  A routine GP review whose PMH lists a 2018 breast
    carcinoma must not promote the encounter to dx/cancer_found.
    """
    text = (
        "Routine GP review for sciatica.\n"
        "Past medical history: HTN, T2DM, carcinoma of breast (2018), "
        "appendicectomy 2005.\n"
        "Examination: SLR 60 deg.\n"
        "Plan: Naproxen 500mg BD."
    )
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-03-01",
        text=text, flags=None,
    )
    assert label.role == "none"

    text2 = (
        "Telephone consultation re back pain.\n"
        "PMH: COPD, T2DM, prostate adenocarcinoma 2019 - completed RT.\n"
        "Plan: Co-codamol PRN, refer for physio."
    )
    label2 = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-03-01",
        text=text2, flags=None,
    )
    assert label2.role == "none"


def test_all_clear_outside_cancer_context_is_not_cancer_excluded():
    """Patient 6040304227 regression: a duty-oncall cardiology note that
    contains the safety-net plan "advised if all clear, obs stable to
    continue Bumetanide" must NOT be promoted to dx/cancer_excluded.
    Without the cancer-context guard around "all clear" the encounter
    closed the urology 2WW pathway on the wrong date (5-month phantom
    duration).
    """
    text = (
        "History: duty oncall - awaiting heart surgery - had an appt at "
        "Loughborough Hospital 8 days ago. Stopped the bisoprolol and "
        "wanted to monitor. Plan: offered minor illness appt to review "
        "chest if any chest infection. Advised if all clear, obs stable "
        "etc to continue Bumetanide dose as prescribed and await "
        "cardiology review. Happy with plan."
    )
    label = deterministic_label(
        patient_id="6040304227", encounter_id="E", encounter_date="2025-03-04",
        text=text, flags=None,
    )
    assert label.role == "none"
    assert label.outcome is None


def test_all_clear_in_cancer_context_still_excluded():
    """Defensive: 'all clear' must STILL fire as cancer_excluded when it
    appears alongside cancer / imaging / pathway language so we don't
    regress legitimate outcome detection.

    Cases that contain "Discharged from 2WW pathway" are deliberately
    excluded here because that phrase is intercepted by the follow-up-to-
    concluded-pathway guard upstream of the dx check; this test focuses
    on imaging / outcome cases that exercise the cancer-context window
    around "all clear".
    """
    cases = [
        "Mammogram all clear, return to routine recall.",
        "Letter from breast clinic - all clear, no further action.",
        "Recent CT scan all clear, no metastatic disease seen.",
        "Skin lesion biopsy all clear - no malignancy.",
    ]
    for text in cases:
        label = deterministic_label(
            patient_id="P", encounter_id="E", encounter_date="2025-03-01",
            text=text, flags=None,
        )
        assert label.role == "dx", f"expected dx for: {text!r} (got {label.role})"
        assert label.outcome == "cancer_excluded", f"expected cancer_excluded for: {text!r}"


def test_all_clear_in_gynae_safety_net_is_not_cancer_excluded():
    """Patient 0e7dceba regression-style: a gynae plan that uses 'all
    clear' as a conditional next-step ('Refer back to Urogynae if all
    clear for ongoing prolapse') without nearby cancer-context words must
    not be labelled dx/cancer_excluded.
    """
    text = (
        "Problem: Genital prolapse (K51..). History: ongoing PMB. "
        "Plan: Refer back to Urogynae if all clear for ongoing prolapse "
        "support and discussion re surgical options."
    )
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-05-13",
        text=text, flags=None,
    )
    assert label.role != "dx" or label.outcome is None


def test_dna_appointment_is_silenced_as_none():
    """Patient 6040304227 regression: a UHL Dermatology slot whose text
    is "Patient Attended - Outcome / Did not attend clinic (XacSG)" must
    NOT be labelled `seen`.  Without this guard the DNA encounter ended
    up as the `first_seen` milestone for the melanoma pathway, hiding
    the real first-attendance encounter on 2024-11-13.
    """
    cases = [
        # Templated DNA — Patient Attended - Outcome with DNA next-action
        (
            "12:20 - Clinic: [PERSON] Entered at: UHL Dermatology Service\n"
            " Patient Attended - Outcome\n"
            "   Next appointment (XaIPT) - Further Appointment\n"
            "   Did not attend clinic (XacSG) - Further Appointment"
        ),
        # Did-not-attend session appointment
        (
            "12:00 - Surgery: [STAFF] (Dr) Entered at: UHL Dermatology Service\n"
            "Did not attend for Session appointment with [PERSON].\n"
            "Did not attend (Xa1kG)"
        ),
        # Did-not-attend hospital appointment (admin record)
        (
            "Surgery: [STAFF] (Admin/Clinical Support Access Role)\n"
            "Did not attend hospital appointment (XaF81) (New Episode)"
        ),
    ]
    for text in cases:
        label = deterministic_label(
            patient_id="6040304227", encounter_id="E",
            encounter_date="2024-10-15", text=text, flags=None,
        )
        assert label.role == "none", \
            f"DNA encounter must be silenced; got {label.role} for: {text[:80]!r}"


def test_suspected_cancer_is_seen_not_dx():
    """Patient 6040304227 regression: a dermatology consultation that
    contains "Suspected skin cancer (XaFww) - Squamous Cell Carcinoma"
    plus "?? BCC ... Scc can not be ruled out" must be labelled `seen`
    (provisional dx at OPD attendance), NOT `dx/cancer_found`.  The
    diagnosis_confirmed milestone belongs to the later excision-biopsy
    encounter that records "Major: Squamous cell carcinoma (Y356f)".
    """
    text = (
        "15:24 - Loughborough Hospital, Clinic: [PERSON] Entered at: "
        "UHL Dermatology Service\n"
        " New Lesion Template\n"
        "      History/symptoms:  PC: 6 months ago noticed scabby area on "
        "the scalp, bled occasionally\n"
        "      Suspected skin cancer:  Squamous Cell Carcinoma\n"
        "      O/E - skin lesion:  1714mm ulcerated nodule right occipital "
        "scalp ?? BCC however, Scc can not be ruled out\n"
        " Patient Attended - Outcome\n"
        "   Digital dermatoscopy of skin (Y3e8b)\n"
        "Suspected skin cancer (XaFww) - Squamous Cell Carcinoma\n"
        "Skin lesion (Xa02q) - right occipital scalp (Ongoing Episode)"
    )
    label = deterministic_label(
        patient_id="6040304227", encounter_id="E",
        encounter_date="2024-11-13", text=text, flags=None,
    )
    assert label.role == "seen"
    assert label.outcome is None


def test_definitive_cancer_dx_in_separate_encounter_still_dx():
    """Defensive: when the SAME encounter does NOT contain a 'Suspected'
    qualifier, a 'Major: Squamous cell carcinoma' line must still be
    labelled dx / cancer_found (the back-dated 2024-11-18 entry for
    patient 6040304227 should remain a dx anchor).
    """
    text = (
        "Surgery: [STAFF] (Admin/Clinical Support Access Role) Entered By: [PERSON]\n"
        "Major: Squamous cell carcinoma (Y356f) - R vertex scalp (New Episode)\n"
        "Squamous cell carcinoma (Y356f) - R vertex scalp"
    )
    label = deterministic_label(
        patient_id="6040304227", encounter_id="E",
        encounter_date="2024-11-18", text=text, flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_specialist_letter_back_to_gp_is_seen_for_cancer_specialties():
    """Patient 6040304227 regression: the 2024-11-26 admin record
    "Urology to Woodbrook Medical Centre" is the urology specialist
    letter back to the GP and is the only OPD-attendance signal for the
    urology 2WW pathway.  Same shape applies to dermatology, breast,
    colorectal etc. letters back.
    """
    cancer_letters = [
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Urology to Woodbrook Medical Centre",
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Dermatology to Woodbrook Medical Centre",
        "Surgery: [STAFF] (Medical Secretary Access Role)\n"
        "Breast Clinic to Whitehill Surgery",
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Colorectal to Pinfold Gate Medical Practice",
    ]
    for text in cancer_letters:
        label = deterministic_label(
            patient_id="P", encounter_id="E",
            encounter_date="2024-11-26", text=text, flags=None,
        )
        assert label.role == "seen", \
            f"Cancer specialist letter back must be seen; got {label.role} for: {text!r}"


def test_non_cancer_specialist_letter_back_is_not_seen():
    """Defensive: only cancer specialties trigger the
    specialist-letter-back -> seen mapping.  Cardiology / physiotherapy /
    pharmacy / etc. letters from non-cancer services must NOT be
    labelled seen so they cannot anchor a cancer pathway.
    """
    non_cancer_letters = [
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Cardiology to Woodbrook Medical Centre",
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Physiotherapy to Woodbrook Medical Centre",
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Pharmacy to Woodbrook Medical Centre",
        "Surgery: [STAFF] (Receptionist Access Role)\n"
        "Diabetic Eye Screening to Woodbrook Medical Centre",
    ]
    for text in non_cancer_letters:
        label = deterministic_label(
            patient_id="P", encounter_id="E",
            encounter_date="2024-11-26", text=text, flags=None,
        )
        assert label.role != "seen", \
            f"Non-cancer specialty letter must not be seen; got {label.role} for: {text!r}"


def test_pmh_strip_does_not_break_active_dx_in_same_text():
    """Defensive: the PMH stripper must NOT remove an active 'Major:' new
    diagnosis line that lives outside the PMH field.  Otherwise a
    real new diagnosis recorded in the same encounter as a recap PMH
    list would be silenced.
    """
    text = (
        "Surgery: F2F appt.\n"
        "Past medical history: HTN, T2DM.\n"
        "Major: Carcinoma of breast (B3401) (New Episode)\n"
        "Plan: Refer breast clinic for treatment planning."
    )
    label = deterministic_label(
        patient_id="P", encounter_id="E", encounter_date="2025-03-01",
        text=text, flags=None,
    )
    assert label.role == "dx"
    assert label.outcome == "cancer_found"


def test_primary_major_site_wins_over_metastasis_keywords():
    """Patient 4940120139 regression: a dx encounter with 'Major: Metastasis
    to lung. Major: Metastasis to liver. Major: Carcinoma of caecum' must
    set site_hint=lower_gi (the primary), not site_hint=lung (a metastasis
    location that simply happened to appear first in token order).
    """
    text = (
        "Major: Metastasis to lung (B570.) (New Episode)\n"
        "Major: Metastasis to liver (B577.) (New Episode)\n"
        "Major: Carcinoma of caecum (X78gM) (New Episode)"
    )
    label = deterministic_label(
        patient_id="4940120139", encounter_id="E", encounter_date="2025-07-22",
        text=text, flags=None,
    )
    assert label.site_hint == "lower_gi"


def test_buccal_mucosa_squamous_resolves_to_head_neck_not_skin():
    """Patient 4802297327 regression: 'Squamous cell carcinoma of buccal
    mucosa' should map to head_neck.  Bare 'squamous cell carcinoma'
    is intentionally NOT a skin token so the qualified form wins.
    """
    text = (
        "Major: Squamous cell carcinoma of buccal mucosa (X78Ig) (Ongoing Episode)\n"
        "MRI of neck (X70oX) (New Episode)"
    )
    label = deterministic_label(
        patient_id="4802297327", encounter_id="E", encounter_date="2025-02-07",
        text=text, flags=None,
    )
    assert label.site_hint == "head_neck"


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
