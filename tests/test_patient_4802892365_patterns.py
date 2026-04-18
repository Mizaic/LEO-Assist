"""VT-LEO-AI-207 .. VT-LEO-AI-209 -- Patient 4802892365 generalisable patterns.

This test suite verifies the three additional detector fixes identified
during the patient 4802892365 review:

  Pattern K -- DI-LEO-AI-215 -- problem-list diagnosis on referral
                                encounter (Major: Ya0ln + Major: X78WM
                                in the same row as the 2WW referral)
  Pattern L -- DI-LEO-AI-216 -- self-narrated past referral inside a
                                follow-up note ("Referred by me on
                                2ww earlier this year, confirmed
                                breast cancer")
  Pattern M -- DI-LEO-AI-217 -- expanded cancer-treatment Read code
                                inventory (XacLJ mastectomy, X40EC
                                wide local excision, Xa8OS partial
                                thyroidectomy, etc.)

The patient's record had an end-to-end breast-cancer pathway:
referral 2025-03-26, first seen 2025-04-28, diagnosis confirmed
same day as the referral via Major:/Problem: lines, mastectomy
2025-07-28, cancer-care review 2025-09-24. The detector previously
missed the diagnosis (Pattern K), spawned a phantom episode for the
follow-up review (Pattern L), and silently dropped the explicit
mastectomy Read code as a treatment signal (Pattern M).
"""

from __future__ import annotations

import importlib

import pytest

# ---------------------------------------------------------------------------
# Pattern K -- problem-list diagnosis overrides referral gate
# (DI-LEO-AI-215, VT-LEO-AI-207)
# ---------------------------------------------------------------------------


class TestPatternKProblemListDxOverridesReferralGate:
    """When an encounter contains BOTH a 2WW referral row AND a
    problem-list malignancy code (Major:/Problem: with Ya0ln, X78WM,
    B-family etc.), diagnosis_confirmed MUST fire on the same
    encounter. The "Major: <code> (New Episode)" prefix is the
    strongest possible signal of a confirmed diagnosis and must not
    be suppressed by the same-encounter referral gate
    (DI-LEO-AI-145).

    Real failing text (patient 4802892365, 2025-03-26 11:56):
      "Fast track referral for suspected breast cancer (XaMeC)
       Choice and booking enhanced services administration (XaMJa)
       2WW Patient awaiting OPD appt.: Yes 2ww breast
       Hospital Fast track referral for suspected breast cancer
       Patient awaiting OPD appt. (9R52.) - 2ww breast
       Major: Invasive carcinoma of breast (Ya0ln) - lobular (New Episode)
       Major: Malignant tumour of breast (X78WM) (New Episode)"
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str, *, eid: str = "E-K", date: str = "2025-03-26") -> dict:
        return {
            "encounter_id": eid,
            "encounter_date": date,
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_problem_list_dx_with_referral_emits_diagnosis(self, detector):
        text = (
            "Fast track referral for suspected breast cancer (XaMeC)\n"
            "Choice and booking enhanced services administration (XaMJa)\n"
            "2WW Patient awaiting OPD appt.: Yes 2ww breast\n"
            "Major: Invasive carcinoma of breast (Ya0ln) - lobular "
            "(New Episode)\n"
            "Major: Malignant tumour of breast (X78WM) (New Episode)"
        )
        rows = [self._row(text)]
        refs, dxs, *_ = detector._classify_text_encounters(rows, set())
        assert len(refs) >= 1, "real referral must still fire"
        assert len(dxs) == 1, (
            f"Major: Ya0ln/X78WM problem-list addition MUST fire "
            f"diagnosis_confirmed even on a same-encounter 2WW row. "
            f"Got refs={refs}, dxs={dxs}"
        )
        dx = dxs[0]
        assert dx.get("diagnosis_source") == "problem_list_code"
        assert dx.get("diagnosis_code") in {"Ya0ln", "X78WM"}

    def test_active_care_code_with_referral_emits_diagnosis(self, detector):
        text = (
            "Fast track referral for suspected breast cancer (XaMeC)\n"
            "Cancer care review (XaKHe)\n"
            "Patient discussed at multidisciplinary team meeting (XaN5C)"
        )
        rows = [self._row(text)]
        _, dxs, *_ = detector._classify_text_encounters(rows, set())
        assert len(dxs) == 1, (
            "Active-cancer-care Read code (XaKHe / XaN5C) is hard "
            "evidence and must fire diagnosis even on a referral encounter"
        )

    def test_referral_with_only_surface_form_cancer_does_not_fire_dx(self, detector):
        """The original DI-LEO-AI-145 trap MUST still hold: a 'Fast
        track referral for suspected lung cancer' note that contains
        the word 'cancer' purely as part of the suspected-referral
        phrase MUST NOT fire diagnosis_confirmed.
        """
        text = (
            "Fast track referral for suspected lung cancer.\n"
            "Symptoms include haemoptysis and weight loss.\n"
            "Plan: refer via 2WW today."
        )
        rows = [self._row(text)]
        _, dxs, *_ = detector._classify_text_encounters(rows, set())
        assert dxs == [], (
            "A surface-form 'cancer' mention in a suspected-referral "
            "phrase must not fire diagnosis_confirmed (DI-LEO-AI-145 trap)"
        )

    def test_problem_list_dx_without_referral_still_fires(self, detector):
        text = (
            "Cancer care review and general catch up.\n"
            "Major: Malignant tumour of breast (X78WM)\n"
            "Plan: continue letrozole, see in 3 months."
        )
        rows = [self._row(text)]
        _, dxs, *_ = detector._classify_text_encounters(rows, set())
        assert len(dxs) == 1, "Problem-list dx without referral still fires"


# ---------------------------------------------------------------------------
# Pattern L -- self-narrated past referral guard
# (DI-LEO-AI-216, VT-LEO-AI-208)
# ---------------------------------------------------------------------------


class TestPatternLSelfNarratedPastReferralGuard:
    """A follow-up note that says "Referred by me on 2ww earlier this
    year", "I referred her last month", "we referred him in Jan",
    "previously referred" MUST be recognised as narrative reference
    to a past referral (NOT a new referral), so it does not spawn a
    phantom EpisodeOfCare.

    Real failing text (patient 4802892365, 2025-09-24 cancer-care
    review):
      "History: Cancer care review and general catch up given recent
       events. Referred by me on 2ww earlier this year, confirmed
       breast cancer. Initially advised she could go on a trial..."
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str) -> dict:
        return {
            "encounter_id": "E-L",
            "encounter_date": "2025-09-24",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_referred_by_me_on_2ww_earlier_matches(self, detector):
        text = "Referred by me on 2ww earlier this year, confirmed breast cancer."
        assert detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text) is not None

    def test_i_referred_last_month_matches(self, detector):
        text = "I referred her to dermatology last month for the lesion."
        assert detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text) is not None

    def test_we_referred_in_jan_matches(self, detector):
        text = "We referred him in Jan via 2WW for suspected lung cancer."
        assert detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text) is not None

    def test_previously_referred_matches(self, detector):
        text = "Patient was previously referred and seen in clinic."
        assert detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text) is not None

    def test_gp_referred_back_in_march_matches(self, detector):
        text = "GP referred via 2WW back in March."
        assert detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text) is not None

    def test_active_referral_text_still_fires_structural(self, detector):
        text = (
            "Outbound referral (XaY59) - Fast track referral for "
            "suspected breast cancer."
        )
        assert (
            detector._RE_STRUCTURAL_REFERRAL.search(text) is not None
        ), "structural keep-list must still recognise real referrals"

    def test_cancer_care_review_followup_does_not_emit_referral(self, detector):
        text = (
            "08:30 - Surgery: BRIDGES, Kirstie (Dr) (Clinical "
            "Practitioner Access Role)\n"
            "Problem: Biopsy of sentinel lymph node (XaF83)\n"
            "Problem: Malignant tumour of breast (X78WM)\n"
            "Problem: Invasive carcinoma of breast (Ya0ln) - lobular\n"
            "Problem: Mastectomy of right breast (XacLJ)\n"
            "History: Cancer care review and general catch up given "
            "recent events. Referred by me on 2ww earlier this year, "
            "confirmed breast cancer. Initially advised she could go "
            "on a trial and have tablets, lumpectomy, then tablets. "
            "Plan changed post MRI as tumour larger than suspected - "
            "had mastectomy July and planned radiotherapy."
        )
        rows = [self._row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        text_generic = [r for r in refs if r.get("referral_subtype") == "text_generic"]
        assert text_generic == [], (
            "Cancer-care-review follow-up that only narrates past "
            "referral activity must not emit a text_generic referral. "
            f"Got {refs}"
        )


# ---------------------------------------------------------------------------
# Pattern M -- expanded cancer-treatment Read code inventory
# (DI-LEO-AI-217, VT-LEO-AI-209)
# ---------------------------------------------------------------------------


class TestPatternMCancerTreatmentReadCodeExpansion:
    """Explicit cancer-surgery / oncology Read codes (XacLJ
    mastectomy, X40EC wide local excision, X20Y4 anterior resection
    of rectum, Xa8OS partial thyroidectomy, Y3c24 robot-assisted
    radical prostatectomy, etc.) MUST fire treatment_started when
    they appear in a Major:/Problem: line. The previous inventory
    only contained 7G055 (skin wide excision) and X90PX (biopsy).
    """

    @pytest.fixture(scope="class")
    def inv(self):
        return importlib.import_module("libs.domains.code_inventories")

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str) -> dict:
        return {
            "encounter_id": "E-M",
            "encounter_date": "2025-07-28",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_breast_surgery_codes_in_inventory(self, inv):
        for code in ("XacLJ", "XacLK", "X40EC", "7H601", "XaF83"):
            assert code in inv.CANCER_TREATMENT_PROCEDURE_CODES, (
                f"Breast cancer surgery Read code {code} must be in "
                "CANCER_TREATMENT_PROCEDURE_CODES"
            )

    def test_bowel_surgery_codes_in_inventory(self, inv):
        for code in ("X20Y4", "XaFB2", "XaZVW", "77132"):
            assert code in inv.CANCER_TREATMENT_PROCEDURE_CODES

    def test_other_cancer_surgery_codes_in_inventory(self, inv):
        for code in ("Y3c24", "Xa8OS", "71102"):
            assert code in inv.CANCER_TREATMENT_PROCEDURE_CODES

    def test_chemo_radio_codes_in_inventory(self, inv):
        for code in ("8BAD0", "8BAD1", "ZV58A"):
            assert code in inv.CANCER_TREATMENT_PROCEDURE_CODES

    def test_legacy_codes_preserved(self, inv):
        assert "7G055" in inv.CANCER_TREATMENT_PROCEDURE_CODES
        assert "X90PX" in inv.CANCER_TREATMENT_PROCEDURE_CODES

    def test_find_helper_returns_xaclj(self, inv):
        text = (
            "Major: Mastectomy of right breast (XacLJ) (New Episode)\n"
            "Major: Biopsy of sentinel lymph node (XaF83) (New Episode)"
        )
        assert inv.find_cancer_treatment_procedure_code(text) in {
            "XacLJ",
            "XaF83",
        }

    def test_mastectomy_problem_line_emits_treatment(self, detector):
        text = (
            "Surgery: RAI, Enju (Miss) (Admin/Clinical Support Access Role)\n"
            "Major: Mastectomy of right breast (XacLJ) (New Episode)\n"
            "Major: Biopsy of sentinel lymph node (XaF83) (New Episode)"
        )
        rows = [self._row(text)]
        _, _, txs, *_ = detector._classify_text_encounters(rows, set())
        assert len(txs) == 1, (
            "Mastectomy Read code (XacLJ) in a Major: problem line must "
            "fire treatment_started"
        )

    def test_anterior_resection_problem_line_emits_treatment(self, detector):
        text = (
            "Surgery: BROWN, Nicola\n"
            "Major: Anterior resection of rectum (X20Y4) (New Episode)"
        )
        rows = [self._row(text)]
        _, _, txs, *_ = detector._classify_text_encounters(rows, set())
        assert len(txs) == 1
