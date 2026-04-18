"""VT-LEO-AI-212 -- Pattern N3 structured-form-field restatement guard.

Verifies DI-LEO-AI-220. Receptionists and administrators routinely
update structured proforma fields whose values carry an embedded date
older than the encounter date. The detector previously emitted fresh
``referral`` and ``first_seen`` milestones on the encounter date,
opening duplicate milestones weeks after the real event already fired.

Canonical patient 4802892365 cases:

  2025-05-13 receptionist note
    "2WW
       Date of First outpatient appointment: 07 Apr 2025 Breast.
       Awaiting needle biopsy."
    Previously: emitted text_generic referral on 2025-05-13.
    Expected: zero referral anchors (real referral was 2025-03-26).

  2025-06-10 receptionist note
    "2WW
       Seen in 2WW Clinic?: Seen in fast track suspected breast
       cancer clinic (XaPyQ) 28 Apr 2025"
    Previously: emitted first_seen on 2025-06-10 via XaPyQ
    specialist-clinic Read code.
    Expected: zero first_seen anchors (real first_seen was the
    2025-04-28 encounter that fires first_seen from its own text).
"""

from __future__ import annotations

import datetime as dt
import importlib

import pytest

from libs.domains.code_inventories import (
    _extract_form_field_dates,
    encounter_restates_past_event,
)


class TestExtractFormFieldDates:
    """Unit tests for the form-field date extractor."""

    def test_extracts_dd_mmm_yyyy_from_form_field_line(self) -> None:
        text = "Date of First outpatient appointment: 07 Apr 2025 Breast."
        assert _extract_form_field_dates(text) == [dt.date(2025, 4, 7)]

    def test_extracts_dd_mmm_yyyy_from_value_with_trailing_text(self) -> None:
        text = (
            "Seen in 2WW Clinic?: Seen in fast track suspected "
            "breast cancer clinic (XaPyQ) 28 Apr 2025"
        )
        assert _extract_form_field_dates(text) == [dt.date(2025, 4, 28)]

    def test_extracts_dd_slash_mm_slash_yyyy_uk_convention(self) -> None:
        text = "Date of referral: 07/05/2024 - via 2WW"
        assert _extract_form_field_dates(text) == [dt.date(2024, 5, 7)]

    def test_extracts_iso_yyyy_mm_dd(self) -> None:
        text = "Diagnosis date: 2025-03-26"
        assert _extract_form_field_dates(text) == [dt.date(2025, 3, 26)]

    def test_returns_empty_for_text_without_colon(self) -> None:
        text = "Patient was seen on 07 Apr 2025 in clinic"
        assert _extract_form_field_dates(text) == []

    def test_returns_empty_for_text_without_date(self) -> None:
        text = "Problem: Repeat medication review"
        assert _extract_form_field_dates(text) == []

    def test_skips_invalid_date_components(self) -> None:
        text = "Field: 32/13/2025 - garbage"
        assert _extract_form_field_dates(text) == []

    def test_extracts_multiple_dates_from_same_line(self) -> None:
        text = "Referral history: referred 07 Apr 2025, seen 28 Apr 2025"
        result = _extract_form_field_dates(text)
        assert dt.date(2025, 4, 7) in result
        assert dt.date(2025, 4, 28) in result


class TestEncounterRestatesPastEvent:
    """Unit tests for the form-field restatement guard predicate."""

    def test_canonical_2025_05_13_form_field_restatement(self) -> None:
        text = (
            "13:17 - Surgery: SILK-MOORE, Karen (Receptionist Access Role)\n"
            "2WW\n"
            "   Date of First outpatient appointment: 07 Apr 2025 "
            "Breast.  Awaiting needle biopsy."
        )
        assert encounter_restates_past_event(text, "2025-05-13") is True

    def test_canonical_2025_06_10_form_field_restatement(self) -> None:
        text = (
            "15:25 - Surgery: SILK-MOORE, Karen (Receptionist Access Role)\n"
            "2WW\n"
            "   Seen in 2WW Clinic?: Seen in fast track suspected "
            "breast cancer clinic (XaPyQ) 28 Apr 2025"
        )
        assert encounter_restates_past_event(text, "2025-06-10") is True

    def test_field_date_within_lookback_is_not_restatement(self) -> None:
        # Field date is 5 days before encounter date -- within the
        # default 14-day lookback, so this is treated as a fresh event
        # (e.g. a clinic admission booked the same week).
        text = "Date of appointment: 08 May 2025"
        assert encounter_restates_past_event(text, "2025-05-13") is False

    def test_field_date_equals_encounter_date_is_not_restatement(self) -> None:
        text = "Seen in 2WW Clinic?: Attended on 13 May 2025"
        assert encounter_restates_past_event(text, "2025-05-13") is False

    def test_text_without_form_field_shape_is_not_restatement(self) -> None:
        # Free-text clinic letter that mentions a past date but does
        # not put it on a form-field-shape line. The guard MUST NOT
        # fire here -- prose narrating past events should be filtered
        # by the existing narrative-referral-reference regex
        # (DI-LEO-AI-201, DI-LEO-AI-216), not by N3.
        text = (
            "Patient was first seen by the breast clinic on 28 Apr "
            "2025 and biopsy was performed."
        )
        assert encounter_restates_past_event(text, "2025-06-10") is False

    def test_empty_text_is_not_restatement(self) -> None:
        assert encounter_restates_past_event("", "2025-06-10") is False

    def test_invalid_encounter_date_returns_false(self) -> None:
        text = "Date of appointment: 07 Apr 2025"
        assert encounter_restates_past_event(text, "not-a-date") is False

    def test_custom_lookback_days(self) -> None:
        text = "Field: 04 May 2025"
        # Encounter on 2025-05-13, field date 9 days earlier
        # Default lookback (14 days): not a restatement
        assert encounter_restates_past_event(text, "2025-05-13") is False
        # 7-day lookback: now considered a restatement
        assert (
            encounter_restates_past_event(
                text, "2025-05-13", lookback_days=7
            )
            is True
        )


# ---------------------------------------------------------------------------
# Integration with _classify_text_encounters
# ---------------------------------------------------------------------------


class TestReferralAndFirstSeenSuppressionOnFormRestatement:
    """End-to-end suppression of fresh referral / first_seen
    milestones on canonical N3 cases.
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str, *, eid: str, date: str) -> dict:
        return {
            "encounter_id": eid,
            "encounter_date": date,
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_2025_05_13_form_restatement_emits_no_referral(self, detector):
        text = (
            "13:17 - Surgery: SILK-MOORE, Karen (Receptionist Access Role)\n"
            "2WW\n"
            "   Date of First outpatient appointment: 07 Apr 2025 "
            "Breast.  Awaiting needle biopsy."
        )
        rows = [self._row(text, eid="E-N3-A", date="2025-05-13")]
        refs, *_ = detector._classify_text_encounters(rows, set())
        assert refs == [], (
            "Form-restatement encounter must emit zero referral "
            f"anchors. Got {refs}"
        )

    def test_2025_06_10_form_restatement_emits_no_first_seen(self, detector):
        text = (
            "15:25 - Surgery: SILK-MOORE, Karen (Receptionist Access Role)\n"
            "2WW\n"
            "   Seen in 2WW Clinic?: Seen in fast track suspected "
            "breast cancer clinic (XaPyQ) 28 Apr 2025"
        )
        rows = [self._row(text, eid="E-N3-B", date="2025-06-10")]
        # Tuple shape: refs, dxs, treatments, specialists, benigns,
        # spec_letters, first_pres, first_seens, care_obstructions
        result = detector._classify_text_encounters(rows, set())
        first_seens = result[7]
        assert first_seens == [], (
            "Form-restatement encounter must emit zero first_seen "
            f"anchors even with XaPyQ specialist-clinic Read code. "
            f"Got {first_seens}"
        )

    def test_real_first_seen_encounter_still_fires(self, detector):
        # Sanity: the original 2025-04-28 first-seen encounter must
        # continue to fire (no over-suppression). This text contains
        # a Read code and the first_seen surface form, but the only
        # date in form-field shape is the encounter date itself.
        text = (
            "Seen in 2WW Clinic?: Seen in fast track suspected "
            "breast cancer clinic (XaPyQ) 28 Apr 2025"
        )
        rows = [self._row(text, eid="E-N3-C", date="2025-04-28")]
        result = detector._classify_text_encounters(rows, set())
        first_seens = result[7]
        assert len(first_seens) == 1, (
            "Source encounter on the same date as the embedded form "
            f"date must still fire first_seen. Got {first_seens}"
        )

    def test_real_text_generic_referral_still_fires(self, detector):
        # Sanity: a fresh referral note on the encounter date must
        # still fire (no over-suppression).
        text = "Refer via 2WW for suspected breast cancer."
        rows = [self._row(text, eid="E-N3-D", date="2025-04-01")]
        refs, *_ = detector._classify_text_encounters(rows, set())
        assert len(refs) == 1, (
            "Fresh referral text on the encounter date must still fire "
            f"text_generic referral. Got {refs}"
        )

    def test_clinic_letter_narrating_past_referral_unaffected_by_n3(
        self, detector
    ):
        # Free-text prose without a Field-shape colon should NOT
        # trigger the N3 guard. Pattern L (DI-LEO-AI-216) handles
        # narrative referral suppression for these cases.
        text = (
            "Patient was first seen by the breast clinic on 28 Apr "
            "2025 and biopsy was performed."
        )
        rows = [self._row(text, eid="E-N3-E", date="2025-06-10")]
        result = detector._classify_text_encounters(rows, set())
        first_seens = result[7]
        # is_first_seen_note matches "first seen" so first_seens may
        # fire here -- but our N3 guard is correctly inert because
        # the past date is not on a Field: line. Pattern L handles
        # the narrative-suppression case separately.
        # Either firing or not firing is acceptable -- the contract
        # for THIS test is that N3 does not over-trigger on prose.
        assert encounter_restates_past_event(text, "2025-06-10") is False
