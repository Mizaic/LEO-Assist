"""VT-LEO-AI-194 .. VT-LEO-AI-199 -- Patient 4643293950 generalisable patterns.

This test suite verifies the seven generalisable detector/builder fixes
identified during the patient 4643293950 review:

  Pattern A -- DI-LEO-AI-205 -- rejected_no_followup episode status
  Pattern B -- DI-LEO-AI-201 -- _RE_FIRST_SEEN attestation guard
  Pattern C -- DI-LEO-AI-202 -- narrative-reference referral guard
  Pattern D -- DI-LEO-AI-202 -- structural referral keep-list
  Pattern E -- DI-LEO-AI-203 -- PMHx benign closure tightening
  Pattern F -- DI-LEO-AI-206 -- exclusive encounter claiming
  Pattern G -- DI-LEO-AI-204 -- care_obstruction anchor + HITL signal

Each pattern was triggered by a real failure mode in patient
4643293950's record (Jan 2024 - Dec 2024 lower-GI 2WW pathway with
multiple referral rejections, a DNA due to mobility, a hospital-
cancelled referral, family/safeguarding concerns, and a confused
"Bowel cancer" PMHx mention that was creating a phantom diagnosis).
The tests below freeze the regex / status-rule behaviour using
representative anonymised text patterns so the pattern fixes do not
regress.
"""
from __future__ import annotations

import importlib

import pytest


# ---------------------------------------------------------------------------
# Pattern B -- _RE_FIRST_SEEN attestation guard (DI-LEO-AI-201, VT-LEO-AI-194)
# ---------------------------------------------------------------------------


class TestPatternBFirstSeenAttestationGuard:
    """Narrative mentions of '2WW clinic' that lack an attestation verb
    (seen|attended|reviewed) MUST NOT emit a first_seen anchor.

    Example failing text (real, patient 4643293950, 2024-11-12):
      "had change in bowel habits - FIT test postive in Jan 2024 -
       referred to 2WW clinic but not attended due to mobility issues"
    """

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    def test_narrative_referred_to_2ww_does_not_match(self, detector):
        text = (
            "had change in bowel habits - FIT test positive in Jan 2024 - "
            "referred to 2WW clinic but not attended due to mobility issues"
        )
        assert detector._RE_FIRST_SEEN.search(text) is None

    def test_narrative_was_referred_lower_gi_2ww_does_not_match(self, detector):
        text = (
            "had FIT positive in jan24 - was referred on lower gi 2ww, "
            "however wasn't seen due to transport issues"
        )
        assert detector._RE_FIRST_SEEN.search(text) is None

    def test_seen_in_fast_track_clinic_still_matches(self, detector):
        text = "Seen in fast track suspected colorectal cancer clinic"
        assert detector._RE_FIRST_SEEN.search(text) is not None

    def test_attended_2ww_clinic_still_matches(self, detector):
        text = "Patient attended 2WW lower GI clinic on 18 Dec 2024"
        assert detector._RE_FIRST_SEEN.search(text) is not None

    def test_seen_in_2ww_short_form_still_matches(self, detector):
        text = "Seen in 2WW Clinic? Yes - 18 Dec 2024"
        assert detector._RE_FIRST_SEEN.search(text) is not None


# ---------------------------------------------------------------------------
# Pattern C+D -- narrative-reference referral guard (DI-LEO-AI-202,
# VT-LEO-AI-195)
# ---------------------------------------------------------------------------


class TestPatternCDNarrativeReferralGuard:
    """A free-text encounter that REFERENCES a past referral
    ("had a previous 2WW", "referred to 2WW clinic but DNA",
    "explained the 2WW referral was rejected") and contains NO
    structural referral artefact (XaY59 outbound referral, PRISM
    pathway accessed, Hospital Fast track referral, Refer via 2WW)
    MUST NOT emit a text_generic referral anchor."""

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    def _make_row(self, text: str, enc_id: str = "E1"):
        return {
            "encounter_id": enc_id,
            "encounter_date": "2024-11-26",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_dna_narrative_does_not_emit_referral(self, detector):
        text = (
            "Noted missed 2WW LGI appt due to transport/ mobility issues "
            "Repeat FIT test sent & requested 2WW referral again"
        )
        rows = [self._make_row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        # Narrative reference WITHOUT a structural cue must not
        # produce a stand-alone text_generic referral.
        text_generic_only = [
            r for r in refs if r.get("referral_subtype") == "text_generic"
        ]
        assert text_generic_only == []

    def test_narrative_with_structural_cue_keeps_referral(self, detector):
        text = (
            "Refer via 2WW LGI pathway. Outbound referral (XaY59) "
            "PRISM 2WW Lower GI Pathway Accessed."
        )
        rows = [self._make_row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        # Structural artefacts present, referral SHOULD be kept.
        assert len(refs) >= 1

    def test_explained_referral_was_rejected_does_not_emit_referral(
        self, detector
    ):
        text = (
            "Explained 2WW referral requested again but got rejected as they "
            "needed new FIT test result"
        )
        rows = [self._make_row(text)]
        refs, *_ = detector._classify_text_encounters(rows, set())
        text_generic_only = [
            r for r in refs if r.get("referral_subtype") == "text_generic"
        ]
        assert text_generic_only == []


# ---------------------------------------------------------------------------
# Pattern E -- PMHx history-of-cancer detection (DI-LEO-AI-203,
# VT-LEO-AI-196)
# ---------------------------------------------------------------------------


class TestPatternEPmhxBenignClosure:
    """A 'Bowel cancer' line that appears under a 'Past medical history'
    header (with no diagnosis date, staging, treatment, or MDT
    discussion) MUST be treated as historical context, not as a new
    diagnosis. The history-of-cancer guard must therefore return True
    for these PMHx-section mentions."""

    @pytest.fixture(scope="class")
    def inv(self):
        return importlib.import_module("libs.domains.code_inventories")

    def test_pmhx_section_with_bowel_cancer_is_history(self, inv):
        text = (
            "Past medical history:\n"
            "CVA - no residual weakness.\n"
            "Hypertension.\n"
            "Bowel cancer.\n"
            "Falls.\n"
            "Benign prostatic hyperplasia."
        )
        assert inv.text_contains_history_of_cancer(text) is True

    def test_pmhx_short_form_pmh_with_malignancy(self, inv):
        text = "PMH: HTN, T2DM, prostate cancer 2018 (in remission)."
        assert inv.text_contains_history_of_cancer(text) is True

    def test_active_diagnosis_text_is_not_history(self, inv):
        text = (
            "Diagnosis: confirmed adenocarcinoma of caecum on biopsy. "
            "MDT outcome: refer to colorectal surgery."
        )
        assert inv.text_contains_history_of_cancer(text) is False


# ---------------------------------------------------------------------------
# Pattern A -- rejected-no-followup status (DI-LEO-AI-205, VT-LEO-AI-197)
# ---------------------------------------------------------------------------


class TestPatternARejectedNoFollowupStatus:
    """An open episode where every referral has subtype 'rejected' AND
    no follow-up referral was filed within the rescue window MUST NOT
    remain 'in_progress' -- it must be marked 'rejected_no_followup'
    so the operations queue surfaces the broken pathway."""

    @pytest.fixture(scope="class")
    def status_mod(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.episode_builder._status"
        )

    def test_all_rejected_no_followup_returns_rejected_status(
        self, status_mod
    ):
        rejected_anchors = [
            {
                "encounter_date": "2024-01-25",
                "referral_subtype": "rejected",
                "encounter_id": "E1",
            },
            {
                "encounter_date": "2024-01-30",
                "referral_subtype": "rejected",
                "encounter_id": "E2",
            },
        ]
        result = status_mod._rejection_followup_status(
            rejected_anchors,
            has_diagnosis=False,
            benign_date=None,
        )
        assert result is not None
        status, hitl_flag, hitl_reason = result
        assert status == "rejected_no_followup"
        assert hitl_flag is True
        assert hitl_reason and "rejected" in hitl_reason.lower()

    def test_rejection_with_followup_referral_returns_none(self, status_mod):
        anchors = [
            {
                "encounter_date": "2024-01-25",
                "referral_subtype": "rejected",
                "encounter_id": "E1",
            },
            {
                "encounter_date": "2024-01-26",
                "referral_subtype": "prism",
                "encounter_id": "E2",
            },
        ]
        result = status_mod._rejection_followup_status(
            anchors,
            has_diagnosis=False,
            benign_date=None,
        )
        assert result is None

    def test_rejection_with_diagnosis_does_not_override(self, status_mod):
        anchors = [
            {
                "encounter_date": "2024-01-25",
                "referral_subtype": "rejected",
                "encounter_id": "E1",
            }
        ]
        result = status_mod._rejection_followup_status(
            anchors,
            has_diagnosis=True,
            benign_date=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Pattern G -- care_obstruction anchor + HITL signal (DI-LEO-AI-204,
# VT-LEO-AI-198)
# ---------------------------------------------------------------------------


class TestPatternGCareObstruction:
    """Narrative evidence of a DNA due to mobility/transport, patient
    or family refusal of investigation/referral, hospital-cancelled
    referrals, safeguarding concerns, or family aggression toward the
    care team MUST emit a care_obstruction anchor and propagate to
    HITL flags on the owning episode."""

    @pytest.fixture(scope="class")
    def detector(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.anchor_detector"
        )

    def _row(self, text: str, enc_id: str = "E1"):
        return {
            "encounter_id": enc_id,
            "encounter_date": "2024-11-12",
            "content_type": "clinical_note",
            "text": text,
            "patient_id": "P-test",
        }

    def test_dna_due_to_mobility_emits_care_obstruction(self, detector):
        text = (
            "referred to 2WW clinic but not attended due to mobility issues - "
            "cannot get into car"
        )
        rows = [self._row(text, "E1")]
        result = detector._classify_text_encounters(rows, set())
        care_obstructions = result[8]
        assert len(care_obstructions) == 1
        assert care_obstructions[0]["encounter_id"] == "E1"

    def test_hospital_retracted_referral_emits_care_obstruction(self, detector):
        text = (
            "we have decided to retract this Referral today. We are unable "
            "to retain referral's awaiting A Fit Score Results."
        )
        rows = [self._row(text, "E2")]
        result = detector._classify_text_encounters(rows, set())
        care_obstructions = result[8]
        assert len(care_obstructions) == 1

    def test_family_aggressive_terminated_call_emits_care_obstruction(
        self, detector
    ):
        text = (
            "Sam from LRI called regarding 2ww sent. His son is refusing to "
            "bring dad to LRI or appointment and also has refused even a "
            "telephone appointment. Told Sam to F off."
        )
        rows = [self._row(text, "E3")]
        result = detector._classify_text_encounters(rows, set())
        care_obstructions = result[8]
        assert len(care_obstructions) == 1

    def test_safeguarding_concern_emits_care_obstruction(self, detector):
        text = (
            "we don't want Frederick's care compromised because of a family "
            "member not engaging - safeguarding concern raised"
        )
        rows = [self._row(text, "E4")]
        result = detector._classify_text_encounters(rows, set())
        care_obstructions = result[8]
        assert len(care_obstructions) == 1

    def test_normal_attendance_does_not_emit_care_obstruction(self, detector):
        text = "Patient attended fast track clinic on 18 Dec 2024 as planned."
        rows = [self._row(text, "E5")]
        result = detector._classify_text_encounters(rows, set())
        care_obstructions = result[8]
        assert care_obstructions == []


# ---------------------------------------------------------------------------
# Pattern F -- exclusive encounter claiming (DI-LEO-AI-206, VT-LEO-AI-199)
# ---------------------------------------------------------------------------


class TestPatternFExclusiveEncounterClaiming:
    """The episode builder MUST link any given encounter to AT MOST one
    EpisodeOfCare. _filter_unclaimed_link_groups removes encounters
    already in BuildContext.claimed_encounters and, after a successful
    link, the encounter ids are added to that set so subsequent
    episodes cannot re-claim them."""

    @pytest.fixture(scope="class")
    def builder(self):
        return importlib.import_module(
            "services.analysis_worker.app.analyzers.episode_builder._builder"
        )

    def test_filter_drops_already_claimed_non_referral_encounter(self, builder):
        groups = [
            (
                [
                    {"encounter_id": "E1", "date": "2024-01-25"},
                    {"encounter_id": "E2", "date": "2024-01-26"},
                ],
                "first_seen",
            ),
            (
                [{"encounter_id": "E3", "date": "2024-02-01"}],
                "treatment_started",
            ),
        ]
        claimed = {"E2"}
        filtered = builder._filter_unclaimed_link_groups(groups, claimed)
        assert filtered == [
            (
                [{"encounter_id": "E1", "date": "2024-01-25"}],
                "first_seen",
            ),
            (
                [{"encounter_id": "E3", "date": "2024-02-01"}],
                "treatment_started",
            ),
        ]
        assert "E1" in claimed and "E3" in claimed

    def test_filter_drops_empty_non_referral_groups(self, builder):
        groups = [
            ([{"encounter_id": "E1"}], "first_seen"),
            ([{"encounter_id": "E2"}], "diagnosis_confirmed"),
        ]
        claimed = {"E1", "E2"}
        filtered = builder._filter_unclaimed_link_groups(groups, claimed)
        assert filtered == []

    def test_referral_milestone_is_protected(self, builder):
        """Referral encounters define episode identity and must be kept
        even if previously claimed by another (overlapping) episode."""
        groups = [([{"encounter_id": "E1"}], "referral")]
        claimed = {"E1"}
        filtered = builder._filter_unclaimed_link_groups(groups, claimed)
        assert filtered == groups

    def test_filter_passes_through_when_no_claims(self, builder):
        groups = [([{"encounter_id": "E1"}], "first_seen")]
        filtered = builder._filter_unclaimed_link_groups(groups, set())
        assert filtered == groups
