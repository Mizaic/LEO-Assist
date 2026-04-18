"""VT-LEO-AI-202 .. VT-LEO-AI-204 -- Patient 4842019832 generalisable patterns.

This test suite verifies the three additional detector fixes identified
during the patient 4842019832 review:

  Pattern H -- DI-LEO-AI-210 -- family-history-of-cancer guard
  Pattern I -- DI-LEO-AI-211 -- boilerplate lab-report referral guidance
  Pattern J -- DI-LEO-AI-212 -- extended narrative-reference guard
                                ('was seen by ENT under 2WW in Jan',
                                 'Write to ENT to clarify')

The patient's record produced 3 EpisodeOfCare nodes; only one (the Dec
2024 head-and-neck 2WW referral seen Jan 2025 with benign LPR /
chronic rhinitis outcome) was real. The other two were phantoms:

  * a 'prostate' closed_benign episode triggered by a normal PSA
    auto-filed result whose disclaimer text says
    "If the PSA value remains elevated above the age specific
     threshold, refer as a 2WW" combined with
    "Reasons for Request: PSA - FH prostate ca." in the clinical
    information block. The patient had FAMILY history of prostate
    cancer (father diagnosed at 75) - he did not, the PSA was 0.77.

  * an 'unknown' in_progress episode triggered by a 2025-06-30
    follow-up that says "Was seen by ENT under 2ww in Jan" plus
    "Write to ENT to clarify that polyp requires no FU". Both are
    narrative references / inter-clinician clarifications, not new
    referral events.

The tests freeze the regex behaviour so the Pattern H/I/J fixes do not
regress.
"""
from __future__ import annotations

import importlib

import pytest


# ---------------------------------------------------------------------------
# Pattern H -- family-history-of-cancer guard (DI-LEO-AI-210, VT-LEO-AI-202)
# ---------------------------------------------------------------------------


class TestPatternHFamilyHistoryGuard:
    """A cancer mention that ONLY appears in a family-history context
    must not trigger a referral or diagnosis anchor for the patient.

    Real failing text (patient 4842019832, 2024-06-19, auto-filed
    PSA result clinical-information block):
      "Reasons for Request: PSA - FH prostate ca."
    Combined with the 2024-06-05 GP note:
      "wanted to get prostate review bloods, has FH of prostate ca -
       father diagnosed at 75 yrs and had radiotherapy and well now."
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @pytest.fixture(scope="class")
    def inv(self):
        return importlib.import_module("libs.domains.code_inventories")

    @staticmethod
    def _row(text: str) -> dict:
        return {
            "encounter_id": "E-FH",
            "encounter_date": "2024-06-19",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_fh_prostate_ca_short_form_matches(self, detector):
        text = "PSA - FH prostate ca."
        assert detector._RE_FAMILY_HISTORY_CANCER.search(text) is not None

    def test_father_diagnosed_with_cancer_matches(self, detector):
        text = (
            "has FH of prostate ca - father diagnosed at 75 yrs and "
            "had radiotherapy and well now"
        )
        assert detector._RE_FAMILY_HISTORY_CANCER.search(text) is not None

    def test_family_history_of_breast_cancer_matches(self, detector):
        text = "Strong family history of breast cancer in mother and aunt."
        assert detector._RE_FAMILY_HISTORY_CANCER.search(text) is not None

    def test_mother_died_of_ovarian_cancer_matches(self, detector):
        text = "Mother died from ovarian cancer aged 60."
        assert detector._RE_FAMILY_HISTORY_CANCER.search(text) is not None

    def test_patient_diagnosis_does_not_match(self, detector):
        text = "Patient diagnosed with prostate cancer in 2018."
        assert detector._RE_FAMILY_HISTORY_CANCER.search(text) is None

    def test_inv_helper_treats_fh_as_history(self, inv):
        text = "PSA - FH prostate ca. Father diagnosed at 75."
        assert inv.text_contains_family_history_of_cancer(text) is True
        assert inv.text_contains_history_of_cancer(text) is True

    def test_fh_only_referral_text_suppressed(self, detector):
        text = (
            "wanted to get prostate review bloods, has FH of prostate ca - "
            "father diagnosed at 75 yrs - counselled on PSA, monitor levels. "
            "Refer as 2WW if elevated."
        )
        rows = [self._row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        text_generic = [
            r for r in refs if r.get("referral_subtype") == "text_generic"
        ]
        assert text_generic == []


# ---------------------------------------------------------------------------
# Pattern I -- boilerplate lab-report referral guidance (DI-LEO-AI-211,
# VT-LEO-AI-203)
# ---------------------------------------------------------------------------


class TestPatternIBoilerplateLabGuidance:
    """An auto-filed lab result that only contains conditional
    referral guidance ("If the PSA value remains elevated...refer as
    a 2WW") MUST NOT fire a text_generic referral.

    Real failing text (patient 4842019832, 2024-06-19):
      "11:47 - Surgery: Auto-filed
       Prostate-specific antigen level (XE25C) 0.77 ng/ml [0 - 4.5]
       PSA values are typically elevated following UTI:
       Please perform repeat PSA testing approximately
       4-6 weeks after treatment. If the PSA value remains
       elevated above the age specific threshold, refer as a
       2WW (Please note that referrals made at the time of UTI
       will be rejected)."
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str) -> dict:
        return {
            "encounter_id": "E-PSA",
            "encounter_date": "2024-06-19",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_boilerplate_psa_guidance_matches(self, detector):
        text = (
            "If the PSA value remains elevated above the age specific "
            "threshold, refer as a 2WW (Please note that referrals "
            "made at the time of UTI will be rejected)."
        )
        assert (
            detector._RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text)
            is not None
        )

    def test_should_be_referred_as_2ww_matches(self, detector):
        text = "If raised the patient should be referred as a 2WW."
        assert (
            detector._RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text)
            is not None
        )

    def test_consider_2ww_referral_if_matches(self, detector):
        text = "Consider a 2WW referral if calprotectin is above 250."
        assert (
            detector._RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text)
            is not None
        )

    def test_referrals_made_at_time_of_uti_matches(self, detector):
        text = (
            "Please note that referrals made at the time of UTI will "
            "be rejected."
        )
        assert (
            detector._RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text)
            is not None
        )

    def test_active_referral_instruction_does_not_match(self, detector):
        text = "Refer this patient via 2WW today for suspected lung cancer."
        assert detector._RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text) is None

    def test_auto_filed_prefix_matches(self, detector):
        text = (
            "11:47 - Surgery: Auto-filed\n"
            "Prostate-specific antigen level (XE25C) 0.77 ng/ml"
        )
        assert detector._RE_AUTO_FILED_PREFIX.search(text) is not None

    def test_auto_filed_psa_disclaimer_does_not_emit_referral(self, detector):
        text = (
            "11:47 - Surgery: Auto-filed\n"
            "Prostate-specific antigen level (XE25C) 0.77 ng/ml [0 - 4.5]\n"
            "PSA values are typically elevated following UTI:\n"
            "Please perform repeat PSA testing approximately\n"
            "4-6 weeks after treatment. If the PSA value remains\n"
            "elevated above the age specific threshold, refer as a\n"
            "2WW (Please note that referrals made at the time of UTI\n"
            "will be rejected).\n"
            "Clinical Information: Reasons for Request: PSA - FH prostate ca."
        )
        rows = [self._row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        text_generic = [
            r for r in refs if r.get("referral_subtype") == "text_generic"
        ]
        assert text_generic == []

    def test_real_referral_with_lab_disclaimer_still_fires(self, detector):
        text = (
            "Outbound referral (XaY59) Fast track referral for suspected "
            "prostate cancer. Note: If the PSA value remains elevated "
            "above the age specific threshold, refer as a 2WW."
        )
        rows = [self._row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        assert len(refs) >= 1


# ---------------------------------------------------------------------------
# Pattern J -- extended narrative-reference guard (DI-LEO-AI-212,
# VT-LEO-AI-204)
# ---------------------------------------------------------------------------


class TestPatternJWasSeenNarrativeGuard:
    """Past-tense seen-narrative ('Was seen by ENT under 2WW in Jan')
    and inter-clinician clarification ('Write to ENT to clarify')
    MUST NOT fire a new text_generic referral.

    Real failing text (patient 4842019832, 2025-06-30 follow-up):
      "Was seen by ENT under 2ww in Jan.
       Found to have laryngopharyngeal reflux with chronic
       rhinosinusitis. ...
       Write to ENT to clarify that polyp requires no FU."
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    @staticmethod
    def _row(text: str) -> dict:
        return {
            "encounter_id": "E-FU",
            "encounter_date": "2025-06-30",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_was_seen_by_ent_under_2ww_matches_narrative(self, detector):
        text = "Was seen by ENT under 2ww in Jan."
        assert (
            detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text)
            is not None
        )

    def test_seen_under_fast_track_clinic_matches_narrative(self, detector):
        text = "Patient seen under fast track clinic last month."
        assert (
            detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text)
            is not None
        )

    def test_write_to_ent_matches_narrative(self, detector):
        text = "Write to ENT to clarify that polyp requires no FU."
        assert (
            detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text)
            is not None
        )

    def test_letter_to_consultant_matches_narrative(self, detector):
        text = "Letter to consultant requesting clarification of plan."
        assert (
            detector._RE_NARRATIVE_REFERRAL_REFERENCE.search(text)
            is not None
        )

    def test_active_referral_does_not_match_narrative(self, detector):
        text = "Outbound referral (XaY59) - Fast track referral for suspected H&N cancer."
        # The structural keep-list still wins regardless of narrative noise.
        assert detector._RE_STRUCTURAL_REFERRAL.search(text) is not None

    def test_was_seen_followup_does_not_emit_referral(self, detector):
        text = (
            "F2F review.\n"
            "1. Had excision of vascular malformation on left hand.\n"
            "2. Was seen by ENT under 2ww in Jan. Found to have "
            "laryngopharyngeal reflux with chronic rhinosinusitis.\n"
            "Plan: Write to ENT to clarify that polyp requires no FU."
        )
        rows = [self._row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        text_generic = [
            r for r in refs if r.get("referral_subtype") == "text_generic"
        ]
        assert text_generic == []
