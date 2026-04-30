"""Unit tests for libs/oncology/care_obstruction.detect_care_obstructions.

Pins the signal hierarchy (rejection > dna > cancellation > access_barrier
> none) and the noise filters so the audit dashboard's "Care obstructions"
tile cannot silently regress when new admin patterns are added.

Test patient examples are drawn from the live cancer cohort (patient
6040304227's prostate / melanoma pathways and others).
"""

from __future__ import annotations

import pytest

from libs.oncology.care_obstruction import (
    CareObstructionMatch,
    detect_care_obstructions,
)


# ---------------------------------------------------------------------------
# Rejection: highest priority, including the canonical XaQgL Read code
# ---------------------------------------------------------------------------


def test_xaqgl_read_code_is_rejection() -> None:
    text = (
        "14:35 - Surgery: [STAFF] (Medical Secretary Access Role)\n"
        " 2WW\n"
        "   Choose and book referral rejected by service provider:  No PSA "
        "or U&E to view\n"
        "Choose and book referral rejected by service provider (XaQgL) - "
        "No PSA or U&E to view"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "rejection"
    assert result.recorded is True
    assert "XaQgL" in result.codes
    assert result.evidence_count == 1
    assert result.type_counts["rejection"] == 1


def test_triage_response_return_to_referrer_is_rejection() -> None:
    text = (
        "Surgery: [STAFF] (Medical Secretary Access Role)\n"
        " 2WW\n"
        "   Choose and book referral rejected by service provider:  "
        "TRIAGE RESPONSE\n"
        "actions\n"
        "outcome:\tReturn to referrer with advice\n"
        "comments: thank you for the 2WW non-site specific referral"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "rejection"


def test_referral_rejected_inappropriate_is_rejection() -> None:
    """Plain "REFERRAL REJECTED - Inappropriate" without an obviously
    non-cancer service-context wrapper still counts as a rejection
    signal.  (When the wrapper IS clearly non-cancer — e.g. "LLR
    Long Term Conditions" — the relatedness filter correctly drops
    it; see :func:`test_ltc_rejection_is_filtered_as_unrelated`.)
    """
    text = (
        "Office Base: [STAFF] (Admin/Clinical Support Access Role)\n"
        "REFERRAL REJECTED - Inappropriate"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "rejection"


def test_ltc_rejection_is_filtered_as_unrelated() -> None:
    """A "REFERRAL REJECTED - Inappropriate" line on a LLR Long Term
    Conditions referral is admin housekeeping for the rehab service,
    not a cancer-pathway obstruction.  The relatedness filter must
    drop it from the headline so the dashboard isn't inflated.
    """
    text = (
        "Office Base: [STAFF] (Admin/Clinical Support Access Role) "
        "Entered at: LLR Long Term Conditions\n"
        "Status Update for Rehabilitation Referral In: Waiting For Assessment\n"
        "REFERRAL REJECTED - Inappropriate"
    )
    result = detect_care_obstructions([text], cancer_type="Lung")
    assert result.signal == "none"
    assert result.unrelated_filtered_count == 1


def test_phlebotomy_duplicate_referral_is_not_rejection() -> None:
    """Defensive: 'referral rejected - duplicate' is admin housekeeping
    on the phlebotomy / SPA pipelines, not a cancer-pathway obstruction.
    Patient 4926916703 has multiple of these — they must NOT be flagged.
    """
    text = (
        "16:48 - Office Base: [STAFF] (Clerical Access Role) Entered at: "
        "LLR Phlebotomy Service\n"
        "Referral In to LLR Phlebotomy Service for phlebotomy: Ended on "
        "08 May 2025 16:52\n"
        "With the Following Intervention(s)\n"
        "Referral Rejected - Duplicate\n"
        "Status Update for phlebotomy Referral In: Waiting For Assessment"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "none"
    assert result.recorded is False


# ---------------------------------------------------------------------------
# DNA: Read codes XacSG / XaF81 / Xa1kG OR encounter flag literal "DNA"
# ---------------------------------------------------------------------------


def test_xacsg_did_not_attend_clinic_is_dna() -> None:
    """Patient 6040304227 melanoma 2024-10-15 DNA in PAS template."""
    text = (
        "12:20 - Clinic: [PERSON] (Clinical Practitioner Access Role) "
        "Entered at: UHL Dermatology Service\n"
        " Patient Attended - Outcome\n"
        "   Next appointment (XaIPT) - Further Appointment\n"
        "   Did not attend clinic (XacSG) - Further Appointment"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "dna"
    assert "XacSG" in result.codes


def test_xaf81_did_not_attend_hospital_is_dna() -> None:
    text = (
        "Surgery: [STAFF] (Admin/Clinical Support Access Role)\n"
        "Did not attend hospital appointment (XaF81) (New Episode)"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "dna"
    assert "XaF81" in result.codes


def test_xa1kg_did_not_attend_session_is_dna() -> None:
    text = (
        "12:00 - Surgery: [STAFF] (Dr) Entered at: UHL Dermatology Service\n"
        "Did not attend for Session appointment with [PERSON].\n"
        "Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "dna"
    assert "Xa1kG" in result.codes


def test_dna_encounter_flag_is_dna_even_with_empty_text() -> None:
    """The EMIS encounter ``flags`` field literally containing 'DNA' is
    a strong DNA signal — used by UHL Dermatology for slot no-shows.
    """
    result = detect_care_obstructions([("", "DNA\nEvent was entered at: UHL Dermatology Service")])
    assert result.signal == "dna"
    assert "dna (encounter flag)" in result.phrases


def test_dna_marked_in_error_is_not_dna() -> None:
    """Defensive: when a DNA was retracted ('Note marked in error') it
    must NOT count as a real DNA.  Patient 6261656266 has this pattern.
    """
    text = (
        "10:21 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
        "Note marked in error: -\n"
        "07 Feb 2024 13:10, Did not attend for registrar appointment "
        "with [PERSON].\n"
        "Diagnosis marked in error: -\n"
        "07 Feb 2024 13:10, Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "none"


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_patient_cancelled_appointment_is_cancellation() -> None:
    text = (
        "12:36 - Surgery: [STAFF] (Clinical Practitioner Access Role)\n"
        "History: task from nurse... 'patient cancelled recent rv apt'"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "cancellation"


def test_hospital_cancelled_appointment_is_cancellation() -> None:
    text = "Cancelled by hospital - clinic full, will rebook"
    result = detect_care_obstructions([text])
    assert result.signal == "cancellation"


# ---------------------------------------------------------------------------
# Access barriers (lowest priority)
# ---------------------------------------------------------------------------


def test_unable_to_contact_patient_is_access_barrier() -> None:
    text = (
        "16:16 - Office Base: [STAFF] (Health Professional Access Role)\n"
        " Triage Template\n"
        "   Medical Information\n"
        "      Clinical management plan:  unable to contact the patient"
    )
    result = detect_care_obstructions([text])
    assert result.signal == "access_barrier"


def test_patient_declined_referral_is_access_barrier() -> None:
    text = "Patient declined the referral despite NICE guidance discussed"
    result = detect_care_obstructions([text])
    assert result.signal == "access_barrier"


def test_lost_to_follow_up_is_access_barrier() -> None:
    text = "Patient lost to follow-up after the third missed appointment"
    result = detect_care_obstructions([text])
    assert result.signal == "access_barrier"


# ---------------------------------------------------------------------------
# None / empty / aggregation
# ---------------------------------------------------------------------------


def test_empty_text_and_empty_iterable_return_none() -> None:
    assert detect_care_obstructions([]).signal == "none"
    assert detect_care_obstructions([""]).signal == "none"
    assert detect_care_obstructions([None]).signal == "none"  # type: ignore[list-item]


def test_unrelated_routine_text_is_none() -> None:
    text = (
        "F2F review - bloods raised BNP, awaiting cardiology appointment, "
        "patient stable on furosemide."
    )
    result = detect_care_obstructions([text])
    assert result.signal == "none"
    assert result.recorded is False


def test_aggregation_picks_strongest_signal() -> None:
    """Mixed bag — a DNA + a rejection + a cancellation in the same window
    must aggregate to ``rejection`` (the strongest), with all three
    counted in ``type_counts``.
    """
    rejected = "Choose and book referral rejected by service provider (XaQgL) - missing PSA"
    dna = "Did not attend clinic (XacSG) - Further Appointment"
    cancelled = "Patient cancelled - rescheduling"
    result = detect_care_obstructions([rejected, dna, cancelled])
    assert result.signal == "rejection"
    assert result.type_counts["rejection"] == 1
    assert result.type_counts["dna"] == 1
    assert result.type_counts["cancellation"] == 1
    assert result.evidence_count == 3
    assert "XaQgL" in result.codes
    assert "XacSG" in result.codes


def test_two_dnas_aggregate_correctly() -> None:
    """Patient 6040304227 melanoma window has TWO DNAs (2024-10-15 +
    2024-10-21).  The dashboard breakdown should show ``dna = 2``.
    """
    dna_1 = "Did not attend clinic (XacSG) - Further Appointment"
    dna_2 = "Did not attend hospital appointment (XaF81) (New Episode)"
    result = detect_care_obstructions([dna_1, dna_2])
    assert result.signal == "dna"
    assert result.type_counts["dna"] == 2
    assert result.evidence_count == 2


def test_signal_priority_is_stable_across_input_order() -> None:
    """Same set of events in different order must produce identical
    aggregate signal and counts.
    """
    rejected = "Choose and book referral rejected by service provider (XaQgL)"
    dna = "Did not attend (Xa1kG)"
    cancel = "Appointment cancelled by patient"
    barrier = "Unable to contact the patient after 3 attempts"
    a = detect_care_obstructions([rejected, dna, cancel, barrier])
    b = detect_care_obstructions([barrier, cancel, dna, rejected])
    assert a.signal == b.signal == "rejection"
    assert a.type_counts == b.type_counts


def test_tuple_event_with_flags_field() -> None:
    """Events may be passed as ``(text, flags)`` tuples — flags is the
    EMIS encounter ``flags`` field which carries the literal ``DNA``
    marker for UHL Dermatology no-shows.
    """
    events = [
        ("Patient Attended - Outcome", "DNA\nLinked to Appointment"),
        ("F2F review, no obstructions", "Face to face"),
    ]
    result = detect_care_obstructions(events)
    assert result.signal == "dna"
    assert result.evidence_count == 1


def test_recorded_flag_matches_signal() -> None:
    assert detect_care_obstructions([""]).recorded is False
    assert (
        detect_care_obstructions(["Did not attend (Xa1kG)"]).recorded is True
    )
    assert (
        detect_care_obstructions(["Choose and book referral rejected by service provider (XaQgL)"]).recorded
        is True
    )


# ---------------------------------------------------------------------------
# Pathway-relatedness filter — defends against noise from non-cancer
# services co-occurring inside the milestone window.
# ---------------------------------------------------------------------------


def test_midwife_dna_in_breast_cancer_window_is_filtered_as_unrelated() -> None:
    """Patient 4246897485 (Breast) had 9 DNAs in the cancer window —
    most were MIDWIFE antenatal/postnatal appointments.  A breast
    cancer patient who DNAs a midwife appointment did NOT obstruct
    her cancer pathway, and the headline must not count it.
    """
    midwife_dna = (
        "12:00 - Surgery: [PERSON], Entered by: [PERSON]\n"
        "Did not attend for Session appointment with Woodbrook Midwife.\n"
        "Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([midwife_dna], cancer_type="Breast")
    assert result.signal == "none"
    assert result.recorded is False
    assert result.evidence_count == 0
    assert result.unrelated_filtered_count == 1


def test_antenatal_check_dna_is_filtered_as_unrelated() -> None:
    """Patient 4246897485 also had a "24+wk an check" DNA — antenatal
    review, not breast cancer pathway.
    """
    antenatal_dna = (
        "15:32 - Surgery: [STAFF] (Midwife Access Role)\n"
        "History: tel call as did not attend clinic appt today for "
        "24+wk an check. VM left - further appt booked for next week."
    )
    result = detect_care_obstructions([antenatal_dna], cancer_type="Breast")
    assert result.signal == "none"
    assert result.unrelated_filtered_count == 1


def test_urgent_treatment_centre_dna_is_filtered_as_unrelated() -> None:
    """Patient 7324271383 (Melanoma) had a DNA at "Loughborough Urgent
    Treatment Centre" — minor injuries / OOH route, not the
    dermatology cancer pathway.
    """
    utc_dna = (
        "15:05 - [PERSON]: Clinician, 6 entered at: Loughborough Urgent "
        "Treatment Centre, Entered by: [PERSON]\n"
        "Did not attend for urgent care appointment with 6 clinician.\n"
        "Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([utc_dna], cancer_type="Melanoma")
    assert result.signal == "none"
    assert result.unrelated_filtered_count == 1


def test_phlebotomy_referral_rejection_is_filtered_as_unrelated() -> None:
    """The "referral rejected - duplicate" pattern is already filtered by
    the rejection-noise regex.  But a ``Referral Rejected -
    Inappropriate`` line that also says ``LLR Phlebotomy Service``
    should also fall out via the unrelated-service classifier.
    """
    phleb_rej = (
        "08:43 - Office Base: [STAFF] Entered at: LLR Phlebotomy Service\n"
        "REFERRAL REJECTED - Inappropriate"
    )
    result = detect_care_obstructions([phleb_rej], cancer_type="Lung")
    assert result.signal == "none"
    assert result.unrelated_filtered_count == 1


def test_2ww_haematology_rejection_is_confirmed_for_lymphoma() -> None:
    """Patient 4200797127 (Lymphoma) had a 2WW haematology referral
    rejected — explicit cancer-pathway markers MUST mark it as
    confirmed-related.
    """
    haem_rej = (
        "12:50 - Surgery: [STAFF] (Medical Secretary Access Role)\n"
        " 2WW\n"
        "   Choose and book referral rejected by service provider:  "
        "TRIAGE RESPONSE\n"
        "actions\n"
        "outcome:\tReturn to referrer with advice\n"
        "comments:\t2WW haematology triage"
    )
    result = detect_care_obstructions([haem_rej], cancer_type="Lymphoma")
    assert result.signal == "rejection"
    assert result.evidence_count == 1
    assert result.confirmed_count == 1
    assert result.unrelated_filtered_count == 0


def test_dermatology_clinic_dna_is_confirmed_for_melanoma() -> None:
    """Patient 6040304227 (Melanoma) had a DNA at "UHL Dermatology
    Service" — the dermatology specialty marker MUST classify this
    as confirmed cancer-pathway related.
    """
    derm_dna = (
        "12:00 - Surgery: [STAFF] (Dr) Entered at: UHL Dermatology Service, "
        "entered by: [PERSON]\n"
        "Did not attend for Session appointment with [PERSON].\n"
        "Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([derm_dna], cancer_type="Melanoma")
    assert result.signal == "dna"
    assert result.confirmed_count == 1


def test_generic_session_dna_with_no_context_is_possible() -> None:
    """A bare ``Did not attend for Session appointment with [PERSON]``
    line with no cancer markers AND no clearly-unrelated service
    context falls into the "possible" bucket — counted toward the
    headline (we'd rather over-count and let the clinician audit
    than miss real obstructions) but NOT marked as confirmed.
    """
    bare_dna = (
        "13:30 - Surgery: [STAFF] (Dr), entered by: [PERSON]\n"
        "Did not attend for Session appointment with [PERSON].\n"
        "Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([bare_dna], cancer_type="Oesophageal")
    assert result.signal == "dna"
    assert result.evidence_count == 1
    assert result.confirmed_count == 0
    assert result.unrelated_filtered_count == 0


def test_mixed_window_aggregates_related_and_unrelated_separately() -> None:
    """Headline should ONLY count the dermatology DNA + the 2WW
    rejection.  The midwife DNA and the UTC DNA should be filtered
    as unrelated and surface only in ``unrelated_filtered_count``.
    """
    events = [
        # Confirmed melanoma (dermatology DNA)
        "Entered at: UHL Dermatology Service. Did not attend (XacSG)",
        # Confirmed 2WW rejection
        "Choose and book referral rejected by service provider (XaQgL) - 2WW review",
        # Unrelated midwife DNA (should be filtered)
        "Did not attend session appointment with Woodbrook Midwife. Did not attend (Xa1kG)",
        # Unrelated UTC DNA (should be filtered)
        "Loughborough Urgent Treatment Centre. Did not attend (Xa1kG)",
        # Possible — bare DNA, no context (should be counted)
        "Did not attend for session appointment with [PERSON]. Did not attend (Xa1kG)",
    ]
    result = detect_care_obstructions(events, cancer_type="Melanoma")
    assert result.signal == "rejection"
    assert result.evidence_count == 3  # 1 derm DNA + 1 rejection + 1 bare DNA
    assert result.confirmed_count == 2  # derm DNA + rejection (bare DNA is "possible")
    assert result.unrelated_filtered_count == 2  # midwife + UTC
    assert result.type_counts["rejection"] == 1
    assert result.type_counts["dna"] == 2


def test_cancer_marker_overrides_unrelated_service_context() -> None:
    """A line that says BOTH ``LLR Phlebotomy`` AND ``2WW`` should
    be treated as confirmed — the positive cancer marker wins.
    Defensive: prevents legit cancer-pathway events being filtered
    when the encounter happened to be administered through a shared
    template that mentions an unrelated service somewhere.
    """
    mixed = (
        "Entered at: LLR Phlebotomy Service. PSA / U&E for 2WW urology "
        "fast track referral. Did not attend (Xa1kG)"
    )
    result = detect_care_obstructions([mixed], cancer_type="Prostate")
    assert result.signal == "dna"
    assert result.confirmed_count == 1
    assert result.unrelated_filtered_count == 0


def test_cancer_type_is_optional_falls_back_to_generic_markers() -> None:
    """If ``cancer_type`` is omitted, only the generic cancer markers
    (2WW, FTR, oncology, biopsy, MDT, NSS pathway) drive the
    confirmed bucket — site-specific specialties no longer trigger
    confirmation but the bare DNA is still classified as "possible".
    """
    events = [
        "Choose and book referral rejected by service provider (XaQgL)",
        "Did not attend for session appointment with [PERSON]. Did not attend (Xa1kG)",
    ]
    result = detect_care_obstructions(events)  # no cancer_type
    assert result.signal == "rejection"
    assert result.confirmed_count == 1
    assert result.evidence_count == 2
