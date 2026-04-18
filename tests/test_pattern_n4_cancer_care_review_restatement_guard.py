"""VT-LEO-AI-402 -- Pattern N4 cancer-care-review restatement guard.

Verifies DI-LEO-AI-402. Pattern K (problem_list_code,
malignancy_term_problem_line, active_cancer_care_code) and the soft
diagnosis sources (cancer_follow_up_template, adjuvant_therapy_drug)
fire ``diagnosis_confirmed`` on routine annual cancer-care-review
encounters whose only "evidence" is the GP keeping the problem list
current and writing a narrative that restates the already-known
cancer history.

Canonical patient 4802892365 case (real episode 1ecfb55618c2a6d2):

  2025-09-24 "Cancer care review and general catch up given recent
              events. Referred by me on 2ww earlier this year,
              confirmed breast cancer. Post mastectomy recovery
              review."
              + Problem-list lines for Ya0ln (lobular carcinoma),
                X78WM (malignant tumour of breast), XacLJ (mastectomy)
              -> Pattern K fires diagnosis_confirmed via the
                 active_cancer_care_code / problem_list_code path.
              -> N4 must suppress the emission entirely. The 2025-09-24
                 anchor must NOT pollute the timeline of the real
                 episode 1ecfb55618c2a6d2 (whose genuine diagnosis
                 happened in mid-May 2025).

N1 (DI-LEO-AI-401) is the floating-group safety net; N4 is the
emission-time guard that prevents the anchor from being created in
the first place. Both layers are kept for defense in depth -- N1
catches sick-note-only restatements that N4 deliberately ignores
(sick notes alone do not typically carry problem-list malignancy
codes, but if they ever do AND lack the cancer-care-review marker,
N1's floating-group filter is the backstop).
"""

from __future__ import annotations

import importlib

import pytest

from libs.domains.code_inventories import (
    encounter_has_new_episode_marker,
    encounter_is_cancer_care_review_restatement,
)


class TestEncounterIsCancerCareReviewRestatement:
    """Unit tests for the N4 cancer-care-review restatement detector."""

    def test_cancer_care_review_template_marker_matches(self) -> None:
        text = (
            "Cancer care review and general catch up given recent events. "
            "Patient remains well."
        )
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_cancer_review_short_marker_matches(self) -> None:
        text = "Annual cancer review completed today."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_known_breast_ca_narrative_matches(self) -> None:
        text = "Phone consult. Patient has known breast ca, on tamoxifen."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_post_mastectomy_recovery_review_matches(self) -> None:
        text = (
            "Routine follow-up. Post mastectomy recovery review going "
            "well, no concerns."
        )
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_referred_by_me_earlier_this_year_matches(self) -> None:
        text = (
            "Cancer care review. Referred by me on 2ww earlier this year, "
            "confirmed breast cancer."
        )
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_pmhx_history_of_cancer_matches(self) -> None:
        text = "PMHx: history of breast carcinoma 2023. Repeat issued."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_history_of_prostate_cancer_matches(self) -> None:
        text = "History of prostate cancer, on 6-monthly PSA monitoring."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_previously_diagnosed_with_colorectal_matches(self) -> None:
        text = "Patient previously diagnosed with colorectal cancer."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_recovering_from_breast_cancer_matches(self) -> None:
        text = "Patient recovering from breast cancer well, see again 6/12."
        assert encounter_is_cancer_care_review_restatement(text) is True

    def test_post_chemotherapy_recovery_matches(self) -> None:
        text = "Post chemotherapy recovery review completed."
        assert encounter_is_cancer_care_review_restatement(text) is True

    # -- INERT cases ------------------------------------------------------

    def test_empty_text_is_inert(self) -> None:
        assert encounter_is_cancer_care_review_restatement("") is False

    def test_none_is_inert(self) -> None:
        assert encounter_is_cancer_care_review_restatement(None) is False

    def test_routine_bp_check_is_inert(self) -> None:
        text = "BP 130/80, no concerns. Repeat issued."
        assert encounter_is_cancer_care_review_restatement(text) is False

    def test_2ww_referral_text_is_inert(self) -> None:
        text = (
            "Refer 2ww breast. Lump on left breast, irregular. Patient "
            "informed of fast track referral for suspected breast cancer."
        )
        assert encounter_is_cancer_care_review_restatement(text) is False

    def test_sicknote_alone_is_inert(self) -> None:
        text = "eMED3 (2010) new statement issued, not fit for work."
        assert encounter_is_cancer_care_review_restatement(text) is False

    # -- EXCEPTION: fresh-diagnosis marker keeps guard inert --------------

    def test_new_episode_marker_keeps_guard_inert(self) -> None:
        text = (
            "Cancer care review and general catch up. Major: Invasive "
            "carcinoma of breast (Ya0ln) - lobular (New Episode). "
            "Discussed with patient."
        )
        assert encounter_is_cancer_care_review_restatement(text) is False

    def test_newly_diagnosed_keeps_guard_inert(self) -> None:
        text = (
            "Cancer care review template completed. Patient newly "
            "diagnosed today, refer to oncology."
        )
        assert encounter_is_cancer_care_review_restatement(text) is False

    def test_diagnosis_confirmed_today_keeps_guard_inert(self) -> None:
        text = (
            "Known breast ca history. Diagnosis confirmed today after "
            "biopsy result."
        )
        assert encounter_is_cancer_care_review_restatement(text) is False


class TestEncounterHasNewEpisodeMarker:
    """Unit tests for the N4 fresh-diagnosis-marker exception."""

    def test_new_episode_parenthetical_matches(self) -> None:
        assert (
            encounter_has_new_episode_marker(
                "Major: Invasive carcinoma of breast (Ya0ln) - lobular "
                "(New Episode). Refer urgently."
            )
            is True
        )

    def test_newly_diagnosed_matches(self) -> None:
        assert (
            encounter_has_new_episode_marker(
                "Patient newly diagnosed with breast cancer today."
            )
            is True
        )

    def test_new_diagnosis_of_matches(self) -> None:
        assert (
            encounter_has_new_episode_marker(
                "New diagnosis of prostate cancer following biopsy."
            )
            is True
        )

    def test_no_marker_returns_false(self) -> None:
        assert (
            encounter_has_new_episode_marker(
                "Routine follow-up. Patient remains well."
            )
            is False
        )

    def test_empty_text_returns_false(self) -> None:
        assert encounter_has_new_episode_marker("") is False


# ---------------------------------------------------------------------------
# Integration: anchor detector suppresses diagnosis_confirmed
# ---------------------------------------------------------------------------


class TestAnchorDetectorSuppressesCancerReviewRestatement:
    """Integration: _classify_text_encounters must NOT emit a
    diagnosis_confirmed anchor when N4 trigger matches and no fresh-
    diagnosis marker is present.
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

    def test_canonical_4802892365_2025_09_24_suppressed(self, detector):
        # The canonical patient 4802892365 2025-09-24 cancer-care-review
        # encounter MUST NOT emit a diagnosis_confirmed anchor under N4.
        text = (
            "08:30 - Surgery: BRIDGES, Kirstie (Dr) "
            "(Clinical Practitioner Access Role)\n"
            "Problem: Biopsy of sentinel lymph node (XaF83)\n"
            "Problem: Malignant tumour of breast (X78WM)\n"
            "Problem: Invasive carcinoma of breast (Ya0ln) - lobular\n"
            "Problem: Mastectomy of right breast (XacLJ)\n"
            "History: Cancer care review and general catch up given recent "
            "events. Referred by me on 2ww earlier this year, confirmed "
            "breast cancer. Post mastectomy recovery review."
        )
        rows = [self._row(text, eid="E-N4-A", date="2025-09-24")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "Pattern N4 must suppress the diagnosis_confirmed anchor "
            "from the canonical 2025-09-24 cancer-care-review encounter "
            "(known-history restatement, no '(New Episode)' marker). "
            f"Got: {diagnoses}"
        )

    def test_pure_cancer_care_review_template_suppressed(self, detector):
        text = (
            "10:00 - Surgery: ISMAIL, Abdul (Dr) "
            "(Clinical Practitioner Access Role)\n"
            "Problem: Invasive carcinoma of breast (Ya0ln)\n"
            "History: Annual cancer care review completed. Patient "
            "remains well on adjuvant therapy."
        )
        rows = [self._row(text, eid="E-N4-B", date="2026-01-15")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "Pure cancer care review template encounter must be "
            "suppressed by N4. "
            f"Got: {diagnoses}"
        )

    def test_post_mastectomy_recovery_review_suppressed(self, detector):
        text = (
            "Surgery: BRIDGES, Kirstie (Dr)\n"
            "Problem: Malignant tumour of breast (X78WM)\n"
            "History: Post mastectomy recovery review going well. "
            "Continue current management."
        )
        rows = [self._row(text, eid="E-N4-C", date="2025-12-01")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "Post-mastectomy recovery review must be suppressed by N4. "
            f"Got: {diagnoses}"
        )

    def test_known_breast_ca_narrative_suppressed(self, detector):
        text = (
            "Surgery: AKHTAR, Mohammed (Mr)\n"
            "Problem: Invasive carcinoma of breast (Ya0ln)\n"
            "History: Phone consult. Patient has known breast ca, "
            "continuing tamoxifen. No concerns."
        )
        rows = [self._row(text, eid="E-N4-D", date="2025-11-12")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "Known-cancer narrative restatement must be suppressed by N4. "
            f"Got: {diagnoses}"
        )

    def test_fresh_diagnosis_NOT_suppressed_by_new_episode_marker(
        self, detector
    ):
        # SAFETY: a genuine fresh diagnosis on the same day as a cancer-
        # care-review template must STILL emit diagnosis_confirmed
        # because the "(New Episode)" marker keeps the N4 guard inert.
        text = (
            "Surgery: BRIDGES, Kirstie (Dr)\n"
            "Major: Invasive carcinoma of breast (Ya0ln) - lobular "
            "(New Episode)\n"
            "History: Cancer care review template loaded. Discussed "
            "diagnosis with patient. MDT referral arranged."
        )
        rows = [self._row(text, eid="E-N4-E", date="2025-04-02")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses, (
            "A fresh '(New Episode)' diagnosis must NOT be suppressed "
            "by N4 even on a cancer-care-review encounter. "
            f"Got: {diagnoses}"
        )

    def test_fresh_diagnosis_NOT_suppressed_by_newly_diagnosed_phrase(
        self, detector
    ):
        text = (
            "Surgery: BRIDGES, Kirstie (Dr)\n"
            "Problem: Malignant tumour of breast (X78WM)\n"
            "History: Cancer care review. Patient newly diagnosed today "
            "after MRI showed mass. Refer urgently."
        )
        rows = [self._row(text, eid="E-N4-F", date="2025-05-19")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses, (
            "'Newly diagnosed' phrase must keep N4 inert and allow "
            "the diagnosis to fire. "
            f"Got: {diagnoses}"
        )

    def test_genuine_first_diagnosis_unaffected(self, detector):
        # Pure fresh-diagnosis encounter, no review template -- N4 must
        # not interfere.
        text = (
            "Major: Invasive carcinoma of breast (Ya0ln) - lobular "
            "(New Episode)\n"
            "Plan: Refer to breast clinic urgently.\n"
            "Discussed diagnosis with patient. MDT referral arranged."
        )
        rows = [self._row(text, eid="E-N4-G", date="2025-04-02")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses, (
            "Pure fresh-diagnosis encounter must always emit "
            "diagnosis_confirmed. "
            f"Got: {diagnoses}"
        )

    def test_2ww_referral_unaffected(self, detector):
        # The cancer term in the body is referral-context, not a
        # restatement. N4 must not fire (no cancer-care-review marker
        # AND no known-cancer narrative).
        text = (
            "Lump on left breast, irregular. Refer 2ww breast. Patient "
            "informed of fast-track referral for suspected breast "
            "cancer."
        )
        rows = [self._row(text, eid="E-N4-H", date="2025-03-26")]
        result = detector._classify_text_encounters(rows, set())
        # Whether diagnosis fires here depends on referral gating
        # (DI-LEO-AI-145), but N4 must not be the suppressor.
        # The N4 helper itself must return False on this text:
        from libs.domains.code_inventories import (
            encounter_is_cancer_care_review_restatement,
        )

        assert (
            encounter_is_cancer_care_review_restatement(
                rows[0]["text"]
            )
            is False
        ), "Pure 2WW referral text must not trigger N4."

    def test_routine_repeat_prescription_unaffected(self, detector):
        text = (
            "Surgery: AKHTAR, Mohammed (Mr) (Pharmacist)\n"
            "Repeat prescription issued for atorvastatin. BP stable."
        )
        rows = [self._row(text, eid="E-N4-I", date="2025-08-12")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "Routine repeat-prescription encounter does not have cancer "
            "evidence in the first place; N4 has nothing to suppress."
        )


class TestN4InteractionWithN1:
    """N4 + N1 interaction: when N4 suppresses emission, the floating-
    group filter never sees the anchor; when N4 doesn't fire (sick-
    note alone, no review template, no known-cancer phrase), N1's
    tagging + filter remain the backstop.
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

    def test_n4_takes_precedence_over_n1_tagging(self, detector):
        # When N4 fires, no anchor is emitted -- so there's nothing for
        # N1 to tag. This is intentional: N4 is the stronger guard.
        text = (
            "Problem: Invasive carcinoma of breast (Ya0ln)\n"
            "History: Cancer care review. Known breast ca, on tamoxifen."
        )
        rows = [self._row(text, eid="E-N4-J", date="2025-09-24")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "N4 must take precedence over N1: when both would trigger, "
            "no diagnosis_confirmed anchor is emitted at all."
        )
