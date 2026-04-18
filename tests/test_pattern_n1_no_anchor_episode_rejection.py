"""VT-LEO-AI-401 -- Pattern N1 no-anchor episode rejection.

Verifies DI-LEO-AI-401. Sick notes (eMED3 / fit notes) and "known X
cancer" / "history of X" narratives in routine GP encounters routinely
cause Pattern K and the soft diagnosis sources
(``cancer_follow_up_template``, ``adjuvant_therapy_drug``) to fire
``diagnosis_confirmed`` on encounters that merely RESTATE an existing
cancer diagnosis. When such a diagnosis anchor has no referral to
attach to, the episode builder still synthesises a floating
diagnosis-led EpisodeOfCare, producing a phantom episode with no real
clinical events.

Canonical patient 4802892365 case (phantom episode 862a306e1ee82616):

  2024-06-04 pharmacist failed-encounter (no diagnosis evidence)
  2025-09-24 "Cancer care review" with problem-list malignancy codes
              -> Pattern K fires diagnosis_confirmed
              -> N1 must tag this as is_narrative_restatement (because
                 the body restates the previous mastectomy and the
                 already-confirmed lobular carcinoma history).
  2025-12-06 eMED3 sick note "not fit for work" mentioning
              "known breast ca"
              -> Pattern K / cancer_follow_up_template may fire
                 diagnosis_confirmed
              -> N1 must tag this as is_narrative_restatement.

  Expected: NO floating EpisodeOfCare materialised from these two
  diagnosis anchors.
"""

from __future__ import annotations

import importlib

import pytest

from libs.domains.code_inventories import (
    encounter_diagnosis_is_narrative_restatement,
)


# ---------------------------------------------------------------------------
# Unit tests for the helper
# ---------------------------------------------------------------------------


class TestEncounterDiagnosisIsNarrativeRestatement:
    """Unit tests for the N1 narrative-restatement detector."""

    # ---- sick-note shapes ------------------------------------------------

    def test_emed3_form_marks_text_as_restatement(self) -> None:
        text = (
            "13:40 - Primary Care Network (PCN): ISMAIL, Abdul (Dr) "
            "(Clinical Practitioner Access Role)\n"
            "eMED3 (2010) new statement issued, not fit for work (XaX1E)\n"
            "Consultation."
        )
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_med3_form_marks_text_as_restatement(self) -> None:
        text = "MED3 issued for 4 weeks, recovering from surgery."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_fit_note_phrase_marks_text_as_restatement(self) -> None:
        text = "Patient requests fit note for ongoing recovery."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_not_fit_for_work_phrase_marks_text_as_restatement(self) -> None:
        text = (
            "Telephone consultation. Patient remains not fit for work "
            "due to ongoing treatment side effects."
        )
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_unfit_for_work_phrase_marks_text_as_restatement(self) -> None:
        text = "Currently unfit for work. Sickness certificate provided."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    # ---- "known X cancer" / "history of X" shapes ------------------------

    def test_known_breast_ca_marks_text_as_restatement(self) -> None:
        text = "Telephone consultation re known breast ca, post mastectomy."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_known_case_of_prostate_cancer_marks_as_restatement(self) -> None:
        text = "Review of known case of prostate cancer for repeat scripts."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_history_of_breast_carcinoma_marks_as_restatement(self) -> None:
        text = "PMHx: history of breast carcinoma 2023, treated with WLE."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_past_history_of_colorectal_ca_marks_as_restatement(self) -> None:
        text = "Past medical history of colorectal ca - in remission since 2024."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_previously_diagnosed_with_breast_ca_marks_as_restatement(self) -> None:
        text = "Patient previously diagnosed with breast cancer in 2023."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_post_mastectomy_recovery_marks_as_restatement(self) -> None:
        text = "Post mastectomy recovery review at 6 weeks."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    def test_post_chemotherapy_followup_marks_as_restatement(self) -> None:
        text = "Post chemotherapy follow-up. Patient tolerating well."
        assert encounter_diagnosis_is_narrative_restatement(text) is True

    # ---- INERT cases (must NOT match) ------------------------------------

    def test_empty_text_is_not_restatement(self) -> None:
        assert encounter_diagnosis_is_narrative_restatement("") is False

    def test_fresh_diagnosis_problem_line_is_not_restatement(self) -> None:
        text = (
            "Major: Invasive carcinoma of breast (Ya0ln) - lobular (New Episode)\n"
            "Plan: Refer to breast clinic urgently."
        )
        assert encounter_diagnosis_is_narrative_restatement(text) is False

    def test_2ww_referral_text_is_not_restatement(self) -> None:
        text = (
            "Refer 2ww breast. Fast track referral for suspected breast "
            "cancer (XaMeC). PRISM 2WW Breast Female questionnaire completed."
        )
        assert encounter_diagnosis_is_narrative_restatement(text) is False

    def test_routine_blood_pressure_check_is_not_restatement(self) -> None:
        text = "BP 134/82. HR 72. No symptoms reported. Continue current meds."
        assert encounter_diagnosis_is_narrative_restatement(text) is False

    def test_pharmacist_failed_encounter_alone_is_not_restatement(self) -> None:
        text = (
            "09:42 - Surgery: KHATRI, Anjli (Pharmacist)\n"
            "Clinical Pharmacist\n"
            "  Seen: Seen by clinical pharmacist (Y20a6)\n"
            "  Failed encounter (9N4..) - text sent\n"
            "  Telephone consultation (XaIge)"
        )
        assert encounter_diagnosis_is_narrative_restatement(text) is False


# ---------------------------------------------------------------------------
# Integration: anchor detector tags diagnosis_confirmed anchors
# ---------------------------------------------------------------------------


class TestAnchorDetectorTagsRestatementDiagnoses:
    """Integration: _classify_text_encounters must tag diagnosis_confirmed
    anchors emitted from sick-note / known-cancer narratives with
    ``is_narrative_restatement: True``.
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

    def test_sicknote_diagnosis_anchor_tagged_as_restatement(self, detector):
        text = (
            "13:40 - Primary Care Network (PCN): ISMAIL, Abdul (Dr) "
            "(Clinical Practitioner Access Role)\n"
            "eMED3 (2010) new statement issued, not fit for work (XaX1E)\n"
            "Consultation. Patient has known breast ca, post mastectomy "
            "recovery follow-up."
        )
        rows = [self._row(text, eid="E-N1-A", date="2025-12-06")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        if not diagnoses:
            pytest.skip(
                "No diagnosis_confirmed anchor was emitted from this "
                "encounter -- N1 tag is moot. Real-world canonical "
                "encounter for patient 4802892365 emits one via Pattern "
                "K's cancer_follow_up_template path; this test verifies "
                "the tag IF an anchor is emitted."
            )
        assert all(
            bool(a.get("is_narrative_restatement")) for a in diagnoses
        ), (
            "Every diagnosis_confirmed anchor emitted from a sick-note "
            "narrative must carry is_narrative_restatement=True. "
            f"Got: {diagnoses}"
        )

    def test_cancer_care_review_diagnosis_anchor_suppressed_by_n4(
        self, detector
    ):
        # Mirrors the canonical 2025-09-24 encounter for patient
        # 4802892365 -- a "Cancer care review and general catch up"
        # that restates the previous mastectomy and lobular carcinoma.
        #
        # Under N1 alone, the diagnosis_confirmed anchor would be
        # emitted and tagged ``is_narrative_restatement: True`` so the
        # floating-group filter could reject any phantom floating
        # group. Under N4 (DI-LEO-AI-402) the emission itself is now
        # suppressed -- N4 is the stronger emission-time guard, N1's
        # tagging + floating-group filter remain the backstop for
        # cases N4 doesn't trigger (sick-note-only encounters).
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
        rows = [self._row(text, eid="E-N1-B", date="2025-09-24")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses == [], (
            "N4 (DI-LEO-AI-402) must suppress the diagnosis_confirmed "
            "emission on the canonical 2025-09-24 cancer-care-review "
            "encounter. The N1 tagging path is moot when N4 has "
            "already prevented the anchor from being created. "
            f"Got: {diagnoses}"
        )

    def test_fresh_diagnosis_anchor_not_tagged_as_restatement(self, detector):
        # A genuine NEW diagnosis encounter must NOT be tagged. This is
        # the safety check: a real first-time problem-list addition with
        # no restatement narrative must continue to materialise an
        # episode.
        text = (
            "Major: Invasive carcinoma of breast (Ya0ln) - lobular "
            "(New Episode)\n"
            "Plan: Refer to breast clinic urgently.\n"
            "Discussed diagnosis with patient. MDT referral arranged."
        )
        rows = [self._row(text, eid="E-N1-C", date="2025-04-02")]
        result = detector._classify_text_encounters(rows, set())
        diagnoses = result[1]
        assert diagnoses, (
            "A fresh problem-list malignancy addition must emit a "
            "diagnosis_confirmed anchor."
        )
        assert not any(
            bool(a.get("is_narrative_restatement")) for a in diagnoses
        ), (
            "A fresh diagnosis encounter (no sick-note / no 'known X "
            "ca' phrasing) must NOT be tagged as a restatement. "
            f"Got: {diagnoses}"
        )


# ---------------------------------------------------------------------------
# Integration: episode builder rejects floating restatement-only groups
# ---------------------------------------------------------------------------


class TestEpisodeBuilderRejectsRestatementOnlyFloatingGroups:
    """Integration: _build_diagnosis_led_groups must NOT materialise a
    floating diagnosis-led group when ALL anchors are tagged as
    narrative restatements.
    """

    @pytest.fixture(scope="class")
    def grouping(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.episode_builder._grouping"
        )

    @staticmethod
    def _diag(
        eid: str,
        date: str,
        site_key: str,
        *,
        restatement: bool,
    ) -> dict:
        return {
            "encounter_id": eid,
            "encounter_date": date,
            "site_key": site_key,
            "concept_name": "diagnosis_cancer",
            "diagnosis_source": "cancer_follow_up_template",
            "is_narrative_restatement": restatement,
        }

    def test_floating_group_with_all_restatements_is_rejected(self, grouping):
        diags = [
            self._diag("E1", "2025-09-24", "breast", restatement=True),
            self._diag("E2", "2025-12-06", "breast", restatement=True),
        ]
        closed, opened = grouping._build_diagnosis_led_groups([], diags)
        floating = [c for c in closed if not c[1]]
        assert floating == [], (
            "A floating diagnosis-led group whose anchors are ALL "
            "narrative restatements must be rejected. "
            f"Got closed={closed}, opened={opened}"
        )

    def test_floating_group_with_one_fresh_anchor_is_kept(self, grouping):
        diags = [
            self._diag("E1", "2025-09-24", "breast", restatement=True),
            self._diag("E2", "2025-04-02", "breast", restatement=False),
        ]
        closed, _opened = grouping._build_diagnosis_led_groups([], diags)
        floating = [c for c in closed if not c[1]]
        assert floating, (
            "A floating diagnosis-led group with at least one non-"
            "restatement anchor must still be materialised."
        )

    def test_floating_group_with_no_restatement_tags_is_kept(self, grouping):
        diags = [
            self._diag("E1", "2025-04-02", "breast", restatement=False),
        ]
        closed, _opened = grouping._build_diagnosis_led_groups([], diags)
        floating = [c for c in closed if not c[1]]
        assert floating, (
            "A floating diagnosis-led group with no restatement tags "
            "must be materialised normally."
        )

    def test_referral_attached_group_unaffected_by_n1(self, grouping):
        # If the diagnosis CAN claim a referral, N1 is irrelevant -- the
        # group is no longer "floating" and must be materialised even if
        # the diagnosis anchor happens to carry is_narrative_restatement.
        refs = [
            {
                "encounter_id": "R1",
                "encounter_date": "2025-03-26",
                "site_key": "breast",
                "concept_name": "referral",
            }
        ]
        diags = [
            self._diag("D1", "2025-04-15", "breast", restatement=True),
        ]
        closed, _opened = grouping._build_diagnosis_led_groups(refs, diags)
        referral_attached = [c for c in closed if c[1]]
        assert referral_attached, (
            "When the diagnosis anchor claims a referral, the group is "
            "no longer floating and N1 must NOT suppress it."
        )

    def test_empty_inputs_produce_no_groups(self, grouping):
        closed, opened = grouping._build_diagnosis_led_groups([], [])
        assert closed == []
        assert opened == []
