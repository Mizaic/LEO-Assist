"""VT-LEO-AI-143 -- first_seen milestone detection and episode wiring.

DI-LEO-AI-145: Verifies that:
  1. _RE_FIRST_SEEN matches fast-track/2WW clinic attendance phrasing.
  2. _RE_FIRST_SEEN does NOT overlap with _RE_REFERRAL patterns.
  3. _classify_text_encounters returns first_seen in the 8th bucket.
  4. _first_seen_link_anchors claims anchors within the episode window
     and returns the earliest date.
  5. MIN_REFERRAL_TO_DIAG_DAYS defaults to 0 (same-day PRISM support).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.analysis_worker.app.analyzers.anchor_detector import (
    _RE_FIRST_SEEN,
    _RE_REFERRAL,
    _classify_text_encounters,
)
from services.analysis_worker.app.analyzers.episode_builder._builder import (
    _first_seen_link_anchors,
)
from services.analysis_worker.app.analyzers.episode_builder import _config as cfg


# ---------------------------------------------------------------------------
# VT-143-TC-001: _RE_FIRST_SEEN matches expected attendance phrases
# ---------------------------------------------------------------------------
class TestFirstSeenRegex:
    SHOULD_MATCH = [
        "Seen in fast track suspected breast cancer clinic (XaPya)",
        "Seen in fast track suspected skin cancer clinic",
        "Seen in 2WW Clinic?: Seen in fast track suspected head and neck cancer clinic",
        "Seen in 2WW clinic",
        "Seen in TWW clinic",
        "Attended fast track suspected lung cancer clinic",
        "Attended 2WW suspected colorectal clinic",
        "Seen in 2WW",
    ]

    SHOULD_NOT_MATCH = [
        "Fast track referral for suspected breast cancer (XaMeC)",
        "PRISM 2WW Breast Female questionnaire started - (finalised: 01 Jan 2025)",
        "fast track referral for suspected skin cancer",
        "2WW Dermatology PRISM to Unknown",
        "urgent cancer referral",
        "2WW proforma submitted",
    ]

    def test_matches_attendance_phrases(self):
        for phrase in self.SHOULD_MATCH:
            assert _RE_FIRST_SEEN.search(phrase), (
                f"_RE_FIRST_SEEN should match: {phrase!r}"
            )

    def test_does_not_match_referral_phrases(self):
        for phrase in self.SHOULD_NOT_MATCH:
            assert not _RE_FIRST_SEEN.search(phrase), (
                f"_RE_FIRST_SEEN should NOT match: {phrase!r}"
            )


# ---------------------------------------------------------------------------
# VT-143-TC-002: first_seen takes priority over generic referral on overlap
# ---------------------------------------------------------------------------
class TestNoRegexOverlap:
    """Clinic-attendance phrases like "Seen in fast track clinic" contain
    the word "fast track" which also appears in _RE_REFERRAL.  The correct
    behaviour is that _classify_text_encounters classifies them as first_seen
    (not as a referral) because is_first_seen_note takes priority over the
    generic referral branch.  This test verifies that priority, NOT that
    the two regexes are mutually exclusive (they intentionally overlap on
    "fast track" as a word).
    """

    FIRST_SEEN_CORPUS = [
        "Seen in fast track suspected breast cancer clinic",
        "Seen in 2WW Clinic?: Seen in fast track suspected head and neck cancer clinic",
        "Attended fast track suspected skin cancer clinic",
    ]

    def _row(self, text: str, enc_id: str) -> dict:
        return {
            "encounter_id": enc_id,
            "encounter_date": "2025-01-01",
            "content_type": "clinical",
            "text": text,
        }

    def test_first_seen_phrases_go_to_first_seen_not_referral(self):
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )
        for i, phrase in enumerate(self.FIRST_SEEN_CORPUS):
            rows = [self._row(phrase, f"enc-{i}")]
            result = _classify_text_encounters(rows, already_coded_ids=set())
            referral_bucket = result[0]
            first_seen_bucket = result[7]
            assert any(r["encounter_id"] == f"enc-{i}" for r in first_seen_bucket), (
                f"Expected first_seen bucket for: {phrase!r}"
            )
            assert not any(
                r["encounter_id"] == f"enc-{i}" for r in referral_bucket
            ), (
                f"first_seen phrase must NOT appear in referral bucket: {phrase!r}"
            )


# ---------------------------------------------------------------------------
# VT-143-TC-003: _classify_text_encounters returns first_seen 8th bucket
# ---------------------------------------------------------------------------
class TestClassifyTextEncountersFirstSeen:
    def _row(self, text: str, enc_id: str = "enc-001") -> dict:
        return {
            "encounter_id": enc_id,
            "encounter_date": "2025-03-26",
            "content_type": "clinical",
            "text": text,
        }

    def test_first_seen_phrase_placed_in_8th_bucket(self):
        rows = [self._row("Seen in fast track suspected breast cancer clinic")]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        assert len(result) == 9, "Must return 9-tuple"
        first_seen_bucket = result[7]
        assert len(first_seen_bucket) == 1
        assert first_seen_bucket[0]["encounter_id"] == "enc-001"

    def test_referral_phrase_not_placed_in_first_seen_bucket(self):
        rows = [self._row(
            "Fast track referral for suspected breast cancer (XaMeC)", "enc-002"
        )]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        first_seen_bucket = result[7]
        assert not any(
            r["encounter_id"] == "enc-002" for r in first_seen_bucket
        ), "GP referral phrase must not appear in first_seen bucket"
        # But it SHOULD appear in referrals (index 0)
        referral_bucket = result[0]
        assert any(r["encounter_id"] == "enc-002" for r in referral_bucket)

    def test_prism_referral_not_in_first_seen_bucket(self):
        rows = [self._row(
            "PRISM 2WW Breast Female questionnaire finalised: 17 Feb 2025",
            "enc-003",
        )]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        first_seen_bucket = result[7]
        assert not any(r["encounter_id"] == "enc-003" for r in first_seen_bucket)

    def test_already_coded_encounter_skipped(self):
        rows = [self._row("Seen in 2WW clinic", "coded-001")]
        result = _classify_text_encounters(rows, already_coded_ids={"coded-001"})
        first_seen_bucket = result[7]
        assert not any(r["encounter_id"] == "coded-001" for r in first_seen_bucket)


# ---------------------------------------------------------------------------
# VT-143-TC-004: _first_seen_link_anchors window claiming
# ---------------------------------------------------------------------------
class TestFirstSeenLinkAnchors:
    def _anchor(self, date_str: str, enc_id: str) -> dict:
        return {
            "encounter_id": enc_id,
            "encounter_date": date_str,
            "concept_name": "Text: first seen at fast-track/2WW clinic",
        }

    def test_anchor_within_window_claimed(self):
        ref_date = date(2025, 1, 10)
        end_date = "2025-03-01"
        anchors = [self._anchor("2025-01-24", "fs-001")]
        claimed, first_date = _first_seen_link_anchors(anchors, ref_date, end_date)
        assert len(claimed) == 1
        assert first_date == "2025-01-24"

    def test_anchor_before_referral_not_claimed(self):
        ref_date = date(2025, 1, 10)
        end_date = "2025-03-01"
        anchors = [self._anchor("2025-01-05", "fs-002")]
        claimed, first_date = _first_seen_link_anchors(anchors, ref_date, end_date)
        assert len(claimed) == 0
        assert first_date is None

    def test_anchor_at_referral_date_claimed(self):
        ref_date = date(2025, 3, 26)
        end_date = "2025-03-26"
        anchors = [self._anchor("2025-03-26", "fs-003")]
        claimed, first_date = _first_seen_link_anchors(anchors, ref_date, end_date)
        assert len(claimed) == 1

    def test_earliest_date_returned_when_multiple(self):
        ref_date = date(2025, 1, 10)
        end_date = "2025-06-01"
        anchors = [
            self._anchor("2025-02-15", "fs-004"),
            self._anchor("2025-01-24", "fs-005"),
        ]
        claimed, first_date = _first_seen_link_anchors(anchors, ref_date, end_date)
        assert first_date == "2025-01-24"

    def test_no_anchors_returns_empty(self):
        claimed, first_date = _first_seen_link_anchors([], date(2025, 1, 1), None)
        assert claimed == []
        assert first_date is None

    def test_no_ref_date_all_anchors_eligible(self):
        anchors = [self._anchor("2024-06-01", "fs-006")]
        claimed, first_date = _first_seen_link_anchors(anchors, None, "2025-01-01")
        assert len(claimed) == 1


# ---------------------------------------------------------------------------
# VT-143-TC-005: MIN_REFERRAL_TO_DIAG_DAYS defaults to 0
# ---------------------------------------------------------------------------
class TestMinReferralToDiagDays:
    def test_default_is_zero(self):
        assert cfg.MIN_REFERRAL_TO_DIAG_DAYS == 0, (
            "DI-LEO-AI-145: MIN_REFERRAL_TO_DIAG_DAYS must default to 0 "
            "to allow same-day PRISM referrals"
        )


# ---------------------------------------------------------------------------
# VT-143-TC-006: referral encounters must not fire diagnosis or benign anchors
# ---------------------------------------------------------------------------
class TestReferralEncounterExcludedFromDiagnosis:
    """DI-LEO-AI-145: 'Fast track referral for suspected X cancer' encounters
    contain cancer terminology with present assertion, but they represent
    SUSPECTED cases only. The same encounter must not appear in both the
    referral bucket AND the diagnosis/benign-closure bucket.

    Two guards:
      a) Text path: _is_referral_enc check in _classify_text_encounters.
      b) Coded path: _referral_enc_ids filter in detect_anchors.
    """

    def _row(self, text: str, enc_id: str) -> dict:
        return {
            "encounter_id": enc_id,
            "encounter_date": "2025-02-17",
            "content_type": "clinical",
            "text": text,
        }

    def test_prism_encounter_not_classified_as_diagnosis(self):
        """PRISM referral + confirmed cancer language: goes to referral only."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )
        prism_text = (
            "PRISM 2WW Breast Female questionnaire finalised: 17 Feb 2025. "
            "Fast track referral for suspected breast cancer. "
            "Confirmed carcinoma of breast."  # worst-case: confirmed language present
        )
        rows = [self._row(prism_text, "prism-enc-001")]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        referral_bucket = result[0]
        diagnosis_bucket = result[1]
        assert any(r["encounter_id"] == "prism-enc-001" for r in referral_bucket), (
            "PRISM encounter must be in referral bucket"
        )
        assert not any(
            r["encounter_id"] == "prism-enc-001" for r in diagnosis_bucket
        ), "PRISM encounter must NOT be in diagnosis bucket"

    def test_generic_referral_encounter_not_classified_as_diagnosis(self):
        """Generic fast-track referral + cancer language: referral only."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )
        ref_text = (
            "Urgent 2WW referral for suspected lung cancer submitted. "
            "Confirmed malignancy of lung."
        )
        rows = [self._row(ref_text, "ref-enc-002")]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        referral_bucket = result[0]
        diagnosis_bucket = result[1]
        assert any(r["encounter_id"] == "ref-enc-002" for r in referral_bucket)
        assert not any(r["encounter_id"] == "ref-enc-002" for r in diagnosis_bucket)

    def test_prism_encounter_not_classified_as_benign_closure(self):
        """PRISM referral + 'no cancer' phrasing: benign closure suppressed."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )
        # Edge-case: GP notes 'no cancer found on previous visit' while completing
        # new referral. Should not close the episode.
        text = (
            "PRISM 2WW questionnaire finalised. "
            "Patient had no cancer found on previous referral but new lump noted."
        )
        rows = [self._row(text, "prism-enc-003")]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        benign_bucket = result[4]
        assert not any(r["encounter_id"] == "prism-enc-003" for r in benign_bucket)

    def test_non_referral_diagnosis_still_fires(self):
        """Standalone confirmed cancer text (no referral) fires as diagnosis."""
        from services.analysis_worker.app.analyzers.anchor_detector import (
            _classify_text_encounters,
        )
        text = "Histology confirmed: invasive carcinoma of breast, grade 2."
        rows = [self._row(text, "hist-enc-004")]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        diagnosis_bucket = result[1]
        assert any(r["encounter_id"] == "hist-enc-004" for r in diagnosis_bucket), (
            "Histology encounter must still fire as diagnosis"
        )

