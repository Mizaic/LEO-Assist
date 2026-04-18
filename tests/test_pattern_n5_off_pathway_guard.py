"""VT-LEO-AI-211 -- Pattern N5 off-pathway non-cancer Problem-header guard.

Verifies DI-LEO-AI-219. When a primary-care encounter carries an
explicit ``Problem:`` header that is unambiguously non-cancer (foreign
travel, vaccination, repeat prescription, sick note, hot flushes
without cancer context, etc.) and the body's cancer mention is
incidental, the detector MUST NOT emit a ``care_obstruction``
milestone even if the underlying _RE_CARE_OBSTRUCTION regex hits.

The canonical failing case is patient 4802892365's 2025-07-01
MMR/Mexico travel-vaccine encounter:

    Problem: Advice on foreign travel (67E..)
    History: Was scheduled for MMR booster today - see notes 03.06.25.
    Partner attended for vaccines and informed me Sue is feeling
    under the weather today so unable to attend for vaccine.
    Travelling to Mexico on Friday. Scheduled for mastectomy on
    29.07.25 - advised postpone vacc until feels well.

The regex matches "unable to attend" and previously emitted a phantom
care_obstruction on the breast pathway -- when the encounter is in
fact a routine travel-vaccine no-show.
"""

from __future__ import annotations

import importlib

import pytest

from libs.domains.code_inventories import encounter_problem_is_off_pathway


class TestEncounterProblemIsOffPathway:
    """Unit tests for the off-pathway Problem-header guard helper."""

    def test_travel_vaccine_problem_header_is_off_pathway(self) -> None:
        text = (
            "Problem: Advice on foreign travel (67E..)\n"
            "History: Was scheduled for MMR booster today - see notes "
            "03.06.25. Partner attended for vaccines and informed me "
            "Sue is feeling under the weather today so unable to "
            "attend for vaccine. Travelling to Mexico on Friday. "
            "Scheduled for mastectomy on 29.07.25 - advised postpone "
            "vacc until feels well."
        )
        assert encounter_problem_is_off_pathway(text) is True

    def test_repeat_medication_problem_header_is_off_pathway(self) -> None:
        text = (
            "Problem: Repeat medication (8B312)\n"
            "History: Pt requesting usual repeats. Cannot have HRT "
            "due to history of breast cancer. Advised to attend for "
            "review in 6 months."
        )
        assert encounter_problem_is_off_pathway(text) is True

    def test_hot_flushes_problem_header_is_off_pathway(self) -> None:
        text = (
            "Problem: Hot flushes (XaBYP)\n"
            "History: Tel appt. Venlafaxine started last month for "
            "hot sweats. Cannot have HRT due to breast cancer."
        )
        assert encounter_problem_is_off_pathway(text) is True

    def test_telephone_consultation_header_is_off_pathway(self) -> None:
        text = (
            "Problem: Telephone consultation (8AR..)\n"
            "History: Patient unable to attend the surgery today. "
            "Will rebook."
        )
        assert encounter_problem_is_off_pathway(text) is True

    def test_cancer_problem_header_is_NOT_off_pathway(self) -> None:
        text = (
            "Problem: Suspected breast cancer (XaJU8)\n"
            "History: Patient declined biopsy and refused 2WW "
            "appointment. Hospital cancelled referral."
        )
        assert encounter_problem_is_off_pathway(text) is False

    def test_oncology_followup_header_is_NOT_off_pathway(self) -> None:
        text = (
            "Problem: Cancer care review (8BAV.)\n"
            "History: Patient unable to attend for chemo today."
        )
        assert encounter_problem_is_off_pathway(text) is False

    def test_2ww_referral_header_is_NOT_off_pathway(self) -> None:
        text = (
            "Problem: 2WW Fast track referral (XaMeC)\n"
            "History: Patient refused colonoscopy."
        )
        assert encounter_problem_is_off_pathway(text) is False

    def test_no_problem_header_is_NOT_off_pathway(self) -> None:
        # A clinic letter or free-text note without an explicit Problem:
        # header MUST NOT be treated as off-pathway -- we only
        # suppress when the encounter intent is clearly stated.
        text = (
            "Patient unable to attend the chemotherapy appointment. "
            "Hospital has cancelled the referral."
        )
        assert encounter_problem_is_off_pathway(text) is False

    def test_mixed_problem_headers_with_one_cancer_is_NOT_off_pathway(self) -> None:
        # If ANY Problem: header is cancer-related the encounter is
        # considered cancer-pathway-relevant.
        text = (
            "Problem: Repeat medication (8B312)\n"
            "Problem: Suspected breast cancer (XaJU8)\n"
            "History: Patient unable to attend."
        )
        assert encounter_problem_is_off_pathway(text) is False

    def test_unknown_non_cancer_problem_header_is_NOT_off_pathway(self) -> None:
        # Conservative default: only KNOWN off-pathway subjects
        # suppress. An unrecognised non-cancer header (e.g. "Earache")
        # leaves the existing behaviour intact.
        text = (
            "Problem: Earache (1B5..)\n"
            "History: Patient unable to attend tomorrow's appointment."
        )
        assert encounter_problem_is_off_pathway(text) is False


# ---------------------------------------------------------------------------
# Integration with _classify_text_encounters
# ---------------------------------------------------------------------------


class TestCareObstructionSuppressionUnderOffPathwayHeader:
    """When the off-pathway guard returns True the detector MUST NOT
    emit a care_obstruction anchor even if the regex would otherwise
    match. When it returns False care_obstruction continues to fire.
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str, *, eid: str = "E-N5", date: str = "2025-07-01") -> dict:
        return {
            "encounter_id": eid,
            "encounter_date": date,
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_canonical_4802892365_2025_07_01_emits_no_care_obstruction(
        self, detector
    ):
        text = (
            "Problem: Advice on foreign travel (67E..)\n"
            "History: Was scheduled for MMR booster today - see notes "
            "03.06.25. Partner attended for vaccines and informed me "
            "Sue is feeling under the weather today so unable to "
            "attend for vaccine. Travelling to Mexico on Friday. "
            "Scheduled for mastectomy on 29.07.25 - advised postpone "
            "vacc until feels well."
        )
        rows = [self._row(text)]
        *_, care_obstructions = detector._classify_text_encounters(rows, set())
        assert care_obstructions == [], (
            "Travel-vaccine encounter must NOT emit care_obstruction. "
            f"Got {care_obstructions}"
        )

    def test_repeat_medication_with_incidental_cancer_emits_no_obstruction(
        self, detector
    ):
        text = (
            "Problem: Repeat medication (8B312)\n"
            "History: Pt requesting usual repeats. Cannot have HRT "
            "due to history of breast cancer. Patient unable to "
            "attend for blood test today."
        )
        rows = [self._row(text, eid="E-RX")]
        *_, care_obstructions = detector._classify_text_encounters(rows, set())
        assert care_obstructions == [], (
            "Repeat-prescription encounter with incidental cancer "
            "mention must NOT emit care_obstruction"
        )

    def test_genuine_cancer_pathway_obstruction_still_fires(self, detector):
        # Sanity check -- the guard MUST NOT over-suppress. A real
        # cancer-pathway DNA / refusal must still emit
        # care_obstruction.
        text = (
            "Problem: Suspected breast cancer (XaJU8)\n"
            "History: Patient refused colonoscopy and declined "
            "the 2WW appointment. Hospital cancelled referral."
        )
        rows = [self._row(text, eid="E-CO")]
        *_, care_obstructions = detector._classify_text_encounters(rows, set())
        assert len(care_obstructions) == 1, (
            "Genuine cancer-pathway refusal must still emit "
            f"care_obstruction. Got {care_obstructions}"
        )

    def test_clinic_letter_without_problem_header_still_fires(self, detector):
        # When there is no Problem: header (e.g. a clinic letter) the
        # guard is inert and the original Pattern G behaviour applies.
        text = (
            "Letter from oncology MDT. Patient unable to attend the "
            "chemotherapy appointment as transport could not be "
            "arranged. Refused alternative slot."
        )
        rows = [self._row(text, eid="E-LT")]
        *_, care_obstructions = detector._classify_text_encounters(rows, set())
        assert len(care_obstructions) == 1, (
            "Clinic letter without Problem header must continue to "
            f"emit care_obstruction. Got {care_obstructions}"
        )
