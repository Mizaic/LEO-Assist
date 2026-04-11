"""Tests for the rule-based encounter textcat component.

Covers:
- admin_only: SMS reminders, SCR entries, booking/registration events
- document_transfer: filed letters, discharge summaries, lab reports
- clinical: GP assessments, prescriptions, examination notes
- clinical_override: ensures strong clinical signals win over doc/admin patterns
- edge cases: empty text, very short text, ambiguous patterns
- ClassificationResult interface compatibility via encounter_classifier.py
"""

from __future__ import annotations

import pytest

from libs.classifiers.encounter_textcat import (
    classify_text,
    reset_pipeline,
    CONTENT_TYPES,
    DEFAULT_LABEL,
)


@pytest.fixture(autouse=True)
def fresh_pipeline():
    """Reset the singleton pipeline before each test so rule-file path changes take effect."""
    reset_pipeline()
    yield
    reset_pipeline()


# ── admin_only ────────────────────────────────────────────────────────────────


class TestAdminOnly:

    def test_sms_sent(self):
        assert (
            classify_text("SMS sent: Reminder for appointment on 12/03/2025")
            == "admin_only"
        )

    def test_sms_prefix_only(self):
        assert classify_text("SMS sent") == "admin_only"

    def test_appointment_reminder(self):
        text = "Reminder for appointment at the surgery on Tuesday 18th March 2025 at 10:00am"
        assert classify_text(text) == "admin_only"

    def test_booking_confirmation(self):
        assert (
            classify_text("Booking confirmation for flu jab clinic sent to patient")
            == "admin_only"
        )

    def test_scr_migration(self):
        assert (
            classify_text(
                "SCR migration completed. Records transferred from legacy system."
            )
            == "admin_only"
        )

    def test_scr_consent(self):
        assert (
            classify_text("Implied consent for Summary Care Record noted.")
            == "admin_only"
        )

    def test_online_visibility(self):
        assert (
            classify_text(
                "Online visibility settings updated. Patient online access enabled."
            )
            == "admin_only"
        )

    def test_data_sharing_notification(self):
        assert (
            classify_text(
                "Data sharing notification: record shared with out-of-hours provider."
            )
            == "admin_only"
        )

    def test_patient_registered(self):
        assert (
            classify_text(
                "Patient registered with practice. New patient registration complete."
            )
            == "admin_only"
        )

    def test_patient_deducted(self):
        assert (
            classify_text(
                "Patient deducted from list following request to transfer to another practice."
            )
            == "admin_only"
        )

    def test_did_not_attend(self):
        assert (
            classify_text("Did not attend - appointment on 05/03/2025 at 09:30")
            == "admin_only"
        )

    def test_dna_short(self):
        assert classify_text("DNA appointment") == "admin_only"

    def test_administrative_correction(self):
        assert (
            classify_text(
                "Administrative correction: back-dated entry to correct coding error."
            )
            == "admin_only"
        )

    def test_access_role(self):
        assert (
            classify_text("Nurse access role entry. No clinical content recorded.")
            == "admin_only"
        )

    def test_empty_text_is_admin(self):
        assert classify_text("") == "admin_only"

    def test_whitespace_only_is_admin(self):
        assert classify_text("   \n\t  ") == "admin_only"

    def test_very_short_text_is_admin(self):
        # max_length=60 in rules; text with no other signals treated as admin
        assert classify_text("DNA") == "admin_only"

    def test_appointment_cancelled(self):
        assert (
            classify_text("Appointment cancelled by patient. Will rebook.")
            == "admin_only"
        )

    def test_made_private(self):
        text = "Event has been made private by another organisation."
        assert classify_text(text) == "admin_only"


# ── document_transfer ─────────────────────────────────────────────────────────


class TestDocumentTransfer:

    def test_discharge_summary(self):
        assert (
            classify_text(
                "Discharge summary received from Northfield General Hospital."
            )
            == "document_transfer"
        )

    def test_clinic_letter_filed(self):
        assert (
            classify_text("Clinic letter filed. From: Cardiology outpatients.")
            == "document_transfer"
        )

    def test_referral_letter_sent(self):
        assert (
            classify_text("Referral letter sent to gastroenterology via e-referral.")
            == "document_transfer"
        )

    def test_letter_received(self):
        assert (
            classify_text(
                "Letter received from haematology department. Filed to record."
            )
            == "document_transfer"
        )

    def test_pathology_report(self):
        assert (
            classify_text("Pathology report received. FBC and U&E results filed.")
            == "document_transfer"
        )

    def test_radiology_report(self):
        assert (
            classify_text("Radiology report received. Chest X-ray report filed.")
            == "document_transfer"
        )

    def test_x_ray_report(self):
        assert (
            classify_text(
                "X-ray report from radiology department filed to patient record."
            )
            == "document_transfer"
        )

    def test_lab_report(self):
        assert (
            classify_text("Lab report: HbA1c result 48 mmol/mol. Filed.")
            == "document_transfer"
        )

    def test_hospital_letter(self):
        assert (
            classify_text(
                "Hospital letter from urology clinic. Filed without annotation."
            )
            == "document_transfer"
        )

    def test_specialist_letter(self):
        assert (
            classify_text("Specialist letter received from oncology. Filed.")
            == "document_transfer"
        )

    def test_outgoing_referral(self):
        assert (
            classify_text("Outgoing referral to physiotherapy. eRS referral sent.")
            == "document_transfer"
        )

    def test_two_week_wait_referral_sent(self):
        assert (
            classify_text(
                "2WW referral sent to colorectal surgery. Urgent suspected cancer pathway."
            )
            == "document_transfer"
        )

    def test_blood_results_received(self):
        assert (
            classify_text("Blood results received from laboratory. Filed to record.")
            == "document_transfer"
        )

    def test_correspondence_filed(self):
        assert (
            classify_text(
                "Correspondence filed: letter from occupational therapy team."
            )
            == "document_transfer"
        )

    def test_report_filed_regex(self):
        assert (
            classify_text("Report received from community mental health team. Filed.")
            == "document_transfer"
        )

    def test_ambulance_report(self):
        assert (
            classify_text("Ambulance report received following 999 call on 01/03/2025.")
            == "document_transfer"
        )


# ── clinical ──────────────────────────────────────────────────────────────────


class TestClinical:

    def test_telephone_consultation(self):
        text = (
            "Telephone consultation. Patient called with ongoing cough for 3 weeks. "
            "No haemoptysis. Advised to monitor and return if not settling."
        )
        assert classify_text(text) == "clinical"

    def test_gp_assessment(self):
        text = (
            "GP appointment. Presenting complaint: chest pain on exertion. "
            "History: 6 weeks duration, worse on climbing stairs. "
            "Examination: heart sounds normal, no murmur. "
            "Plan: refer to cardiology urgently."
        )
        assert classify_text(text) == "clinical"

    def test_blood_pressure_reading(self):
        text = "Hypertension review. BP 145/92. Discussed lifestyle modifications. Ramipril 5mg od continued."
        assert classify_text(text) == "clinical"

    def test_medication_review(self):
        text = (
            "Medication review. Reviewed current medications. "
            "Metformin 500mg bd for type 2 diabetes. HbA1c stable at 52 mmol/mol. "
            "Continue current regime."
        )
        assert classify_text(text) == "clinical"

    def test_prescription_issued(self):
        text = "Acute prescription issued. Amoxicillin 500mg tds for 7 days for chest infection."
        assert classify_text(text) == "clinical"

    def test_on_examination_notation(self):
        text = "Sore throat. O/E throat erythematous, no exudate. FeverPAIN score 2. Advised analgesia."
        assert classify_text(text) == "clinical"

    def test_hx_dx_notation(self):
        text = "Hx: recurrent UTI symptoms, dysuria and frequency. Dx: UTI. Rx: trimethoprim 200mg bd."
        assert classify_text(text) == "clinical"

    def test_plan_section(self):
        text = "Lower back pain. O/E: mild lumbar tenderness, full range of movement. Plan: physiotherapy referral."
        assert classify_text(text) == "clinical"

    def test_presenting_complaint(self):
        text = "Presenting complaint: fatigue and weight loss over 3 months. Investigations ordered."
        assert classify_text(text) == "clinical"

    def test_examination_reveals(self):
        text = "Examination reveals palpable lymph node in right axilla. Urgent 2WW referral to breast surgery."
        assert classify_text(text) == "clinical"

    def test_unknown_text_defaults_to_clinical(self):
        # Anything unrecognised should default to clinical (conservative)
        text = "Follow up discussion with patient regarding ongoing situation."
        assert classify_text(text) == "clinical"

    def test_ambiguous_short_clinical_text(self):
        # Short but explicitly clinical
        text = "BP 130/80. Stable."
        assert classify_text(text) == "clinical"


# ── clinical_override: strong clinical wins over doc/admin patterns ────────────


class TestClinicalOverride:

    def test_discharge_summary_with_gp_bp_annotation(self):
        """GP has annotated a discharge summary with clinical measurements."""
        text = (
            "Discharge summary received. O/E BP 138/84. "
            "Reviewed by GP. Medications reconciled. Plan: continue ramipril."
        )
        assert classify_text(text) == "clinical"

    def test_clinic_letter_with_gp_examination(self):
        """Clinic letter filed but GP has added examination notes."""
        text = (
            "Clinic letter from urology. O/E: abdomen soft, no tenderness. "
            "Prescribed tamsulosin 400mcg od. Review in 3 months."
        )
        assert classify_text(text) == "clinical"

    def test_letter_with_medication_prescribed(self):
        text = (
            "Letter received from haematology. Prescribed hydroxycarbamide 500mg od "
            "following review. Follow up bloods arranged."
        )
        assert classify_text(text) == "clinical"

    def test_appointment_reminder_with_clinical_content(self):
        """Rare edge case: admin framing but GP has added clinical content."""
        text = (
            "Appointment reminder sent. However also noted: BP 150/95 at walk-in. "
            "Plan: start amlodipine 5mg od."
        )
        assert classify_text(text) == "clinical"

    def test_prescription_wins_over_admin_language(self):
        text = "Patient did not attend. New prescription issued: salbutamol inhaler 100mcg prn."
        assert classify_text(text) == "clinical"


# ── ClassificationResult interface ───────────────────────────────────────────


class TestClassificationResultInterface:

    def test_classify_encounter_returns_dataclass(self):
        from services.api.app.services.encounter_classifier import (
            classify_encounter,
            ClassificationResult,
        )

        result = classify_encounter(
            "Patient presents with back pain. O/E: lumbar tenderness."
        )
        assert isinstance(result, ClassificationResult)
        assert result.content_type == "clinical"
        assert result.model_a_type == "rule_textcat"
        assert result.consensus_agreement is True

    def test_classify_encounter_admin(self):
        from services.api.app.services.encounter_classifier import classify_encounter

        result = classify_encounter("SMS sent: Reminder for appointment tomorrow.")
        assert result.content_type == "admin_only"
        assert result.clinical_significance == "low"

    def test_classify_encounter_document_transfer(self):
        from services.api.app.services.encounter_classifier import classify_encounter

        result = classify_encounter(
            "Discharge summary filed. From: cardiology. No GP annotation."
        )
        assert result.content_type == "document_transfer"

    def test_classify_encounter_empty_returns_admin(self):
        from services.api.app.services.encounter_classifier import classify_encounter

        result = classify_encounter("")
        assert result.content_type == "admin_only"

    def test_build_patient_encounter_index_counts(self):
        from services.api.app.services.encounter_classifier import (
            build_patient_encounter_index,
        )

        encounters = [
            {"id": "e1", "text": "SMS sent: appointment reminder"},
            {"id": "e2", "text": "Discharge summary filed from hospital."},
            {
                "id": "e3",
                "text": "Presenting complaint: cough. O/E chest clear. Plan: reassure.",
            },
        ]
        index = build_patient_encounter_index(
            "patient-1", encounters, run_id="test-run"
        )
        assert index.total == 3
        assert index.admin_count == 1
        assert index.document_transfer_count == 1
        assert index.clinical_count == 1

    def test_build_patient_encounter_index_empty_text_is_admin(self):
        from services.api.app.services.encounter_classifier import (
            build_patient_encounter_index,
        )

        encounters = [{"id": "e1", "text": ""}]
        index = build_patient_encounter_index("patient-1", encounters)
        assert index.admin_count == 1
        assert index.clinical_count == 0

    def test_result_fields_are_serialisable(self):
        """Ensure the result can be round-tripped via dataclasses.asdict (for checkpoint store)."""
        import dataclasses
        from services.api.app.services.encounter_classifier import (
            classify_encounter,
            ClassificationResult,
        )

        result = classify_encounter(
            "Patient seen for medication review. Metformin dose reviewed."
        )
        d = dataclasses.asdict(result)
        reconstructed = ClassificationResult(**d)
        assert reconstructed.content_type == result.content_type


# ── doc.cats structure ────────────────────────────────────────────────────────


class TestDocCats:

    def test_doc_cats_one_hot(self):
        """doc.cats must always contain exactly the three labels with one-hot scores."""
        import spacy
        from libs.classifiers.encounter_textcat import _get_pipeline

        nlp = _get_pipeline()
        doc = nlp("SMS sent to patient reminding them of appointment.")
        assert set(doc.cats.keys()) == set(CONTENT_TYPES)
        assert sum(doc.cats.values()) == pytest.approx(1.0)
        assert doc.cats["admin_only"] == 1.0
        assert doc.cats["document_transfer"] == 0.0
        assert doc.cats["clinical"] == 0.0

    def test_default_label_is_clinical(self):
        assert DEFAULT_LABEL == "clinical"


# ── Anchor detector (VT-001-TC-004) ──────────────────────────────────────────


class TestAnchorDetector:
    """Verify detect_anchors() identifies milestone encounters from SNOMED DOCUMENTS.

    Tests are fully mock-based — no live Neo4j required. They exercise the
    core logic in services/analysis_worker/app/analyzers/anchor_detector.py.
    """

    def _make_client(self, coded_rows=None, expanded_rows=None):
        from unittest.mock import MagicMock

        client = MagicMock()

        def _run(query, **kwargs):
            if "DOCUMENTS" in query:
                return coded_rows or []
            return expanded_rows or []

        client.run.side_effect = _run
        return client

    def test_referral_anchor_detected_from_fast_track_concept(self):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )
        from libs.domains.ncda_concept_sets import FAST_TRACK_REFERRAL_IDS

        referral_id = next(iter(FAST_TRACK_REFERRAL_IDS))
        coded = [
            {
                "encounter_id": "enc-001",
                "encounter_date": "2024-03-01",
                "concept_id": referral_id,
                "concept_name": "Referral to cancer service",
                "confidence": 0.95,
                "source": "provisional",
                "evidence": "",
            }
        ]
        client = self._make_client(coded_rows=coded)
        result = detect_anchors("pat-001", "2024-01-01", "2024-12-31", client)

        assert len(result.referral_anchors) == 1
        assert result.referral_anchors[0]["encounter_id"] == "enc-001"
        assert result.detection_method == "concept"

    def test_no_anchors_when_no_coded_encounters(self):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )

        client = self._make_client(coded_rows=[])
        result = detect_anchors("pat-002", "2024-01-01", "2024-12-31", client)

        assert result.referral_anchors == []
        assert result.diagnosis_anchors == []
        assert result.treatment_anchors == []
        assert result.specialist_visit_anchors == []
        assert result.detection_method == "none"

    def test_diagnosis_anchor_detected_from_cancer_type_concept(self):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )
        from libs.domains.ncda_concept_sets import CANCER_TYPE_IDS

        cancer_id = next(iter(CANCER_TYPE_IDS))
        coded = [
            {
                "encounter_id": "enc-010",
                "encounter_date": "2024-06-15",
                "concept_id": cancer_id,
                "concept_name": "Malignant neoplasm of colon",
                "confidence": 0.98,
                "source": "confirmed",
                "evidence": "",
            }
        ]
        client = self._make_client(coded_rows=coded)
        result = detect_anchors("pat-003", "2024-01-01", "2024-12-31", client)

        assert len(result.diagnosis_anchors) == 1
        assert result.diagnosis_anchors[0]["concept_id"] == cancer_id

    def test_same_encounter_deduped_within_anchor_type(self):
        """Same encounter_id must appear at most once per anchor list."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )
        from libs.domains.ncda_concept_sets import FAST_TRACK_REFERRAL_IDS

        referral_id = next(iter(FAST_TRACK_REFERRAL_IDS))
        coded = [
            {
                "encounter_id": "enc-dup",
                "encounter_date": "2024-04-01",
                "concept_id": referral_id,
                "concept_name": "Referral A",
                "confidence": 0.9,
                "source": "provisional",
                "evidence": "",
            },
            {
                "encounter_id": "enc-dup",
                "encounter_date": "2024-04-01",
                "concept_id": referral_id,
                "concept_name": "Referral B (same encounter, different row)",
                "confidence": 0.85,
                "source": "provisional",
                "evidence": "",
            },
        ]
        client = self._make_client(coded_rows=coded)
        result = detect_anchors("pat-004", "2024-01-01", "2024-12-31", client)

        assert (
            len(result.referral_anchors) == 1
        ), "Duplicate encounter_id must be deduplicated"

    def test_window_expansion_sets_expanded_dates(self):
        """With a referral anchor present, expanded_start and expanded_end must be set."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            detect_anchors,
        )
        from libs.domains.ncda_concept_sets import FAST_TRACK_REFERRAL_IDS

        referral_id = next(iter(FAST_TRACK_REFERRAL_IDS))
        coded = [
            {
                "encounter_id": "enc-win",
                "encounter_date": "2024-06-01",
                "concept_id": referral_id,
                "concept_name": "Fast track referral",
                "confidence": 0.92,
                "source": "provisional",
                "evidence": "",
            }
        ]
        client = self._make_client(coded_rows=coded, expanded_rows=[])
        result = detect_anchors(
            "pat-005", "2024-01-01", "2024-12-31", client, expand_months=3
        )

        assert result.expanded_start is not None
        assert result.expanded_end is not None
        assert result.expanded_start < "2024-06-01"
        assert result.expanded_end > "2024-06-01"
