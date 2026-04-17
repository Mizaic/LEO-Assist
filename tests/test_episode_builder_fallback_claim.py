"""VT-LEO-AI-137 - Two-pass referral matching (strict + fallback).

Covers the fallback-claim behaviour introduced under DI-LEO-AI-136 to
address under-counting of 2WW referrals on NCDA-confirmed cancer
episodes: Pass 1 keeps the legacy strict-same-site match; Pass 2
claims any unclaimed referral inside the lookback window regardless of
site key when the strict pass left a diagnosis unmatched.
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.analyzers.episode_builder._grouping import (
    _build_diagnosis_led_groups,
    _find_best_referral,
)


def _ref(d: str, concept: str = "breast 2WW") -> dict:
    return {
        "encounter_id": f"e-{d}",
        "encounter_date": d,
        "concept_name": concept,
    }


def _diag(d: str, concept: str = "breast cancer") -> dict:
    return {
        "encounter_id": f"d-{d}",
        "encounter_date": d,
        "concept_name": concept,
    }


class TestFindBestReferralFallback:
    def test_strict_pass_requires_site_match(self):
        """VT-137-TC-001: Pass 1 does not accept a mismatched-site ref."""
        diag = date(2024, 5, 1)
        refs = [_ref("2024-04-01", concept="suspected lung cancer")]
        assert (
            _find_best_referral(diag, "breast", refs, set(), require_site_match=True)
            is None
        )

    def test_fallback_pass_accepts_any_site(self):
        """VT-137-TC-002: Pass 2 claims the referral regardless of site."""
        diag = date(2024, 5, 1)
        refs = [_ref("2024-04-01", concept="suspected lung cancer")]
        result = _find_best_referral(
            diag, "breast", refs, set(), require_site_match=False
        )
        assert result is not None
        idx, ref_date = result
        assert idx == 0
        assert ref_date == date(2024, 4, 1)

    def test_fallback_still_respects_min_gap(self):
        """VT-137-TC-003: same-day referrals rejected in both passes."""
        diag = date(2024, 5, 1)
        refs = [_ref("2024-05-01", concept="suspected lung cancer")]
        assert (
            _find_best_referral(diag, "breast", refs, set(), require_site_match=False)
            is None
        )

    def test_fallback_still_respects_lookback(self):
        """VT-137-TC-004: referrals outside DIAG_LOOKBACK_DAYS rejected."""
        diag = date(2024, 5, 1)
        refs = [_ref("2021-01-01", concept="suspected lung cancer")]
        assert (
            _find_best_referral(diag, "breast", refs, set(), require_site_match=False)
            is None
        )


class TestTwoPassGrouping:
    def test_strict_match_produces_strict_site_method(self):
        """VT-137-TC-005: DI-136 audit field 'strict_site' when site matches."""
        refs = [_ref("2024-04-10", concept="breast 2WW")]
        diags = [_diag("2024-05-01", concept="breast carcinoma")]
        closed, _open = _build_diagnosis_led_groups(refs, diags)
        assert len(closed) == 1
        site, ref_anchors, diag_anchors, method = closed[0]
        assert site == "breast"
        assert len(ref_anchors) == 1
        assert method == "strict_site"

    def test_fallback_match_produces_fallback_method(self):
        """VT-137-TC-006: floating diagnosis claims mismatched-site
        referral in Pass 2 and is tagged 'fallback_any_site'. The
        referral concept extracts to a different specific site
        (``lung``) so Pass 1 must reject it; Pass 2 then claims it."""
        refs = [_ref("2024-04-10", concept="suspected lung cancer")]
        diags = [_diag("2024-05-01", concept="breast carcinoma")]
        closed, _open = _build_diagnosis_led_groups(refs, diags)
        assert len(closed) == 1
        site, ref_anchors, _diags, method = closed[0]
        assert len(ref_anchors) == 1
        assert method == "fallback_any_site"

    def test_no_referral_produces_none_method(self):
        """VT-137-TC-007: truly floating diagnosis remains untagged as
        strict_site; method is 'none' so persisted ep.referral_date is
        NULL and ep.referral_match_method is 'none'."""
        refs: list[dict] = []
        diags = [_diag("2024-05-01", concept="breast carcinoma")]
        closed, _open = _build_diagnosis_led_groups(refs, diags)
        assert len(closed) == 1
        _site, ref_anchors, _diags, method = closed[0]
        assert ref_anchors == []
        assert method == "none"

    def test_strict_precedence_over_fallback(self):
        """VT-137-TC-008: a site-matched referral wins even when a
        different-site referral sits closer in time."""
        refs = [
            _ref("2024-03-01", concept="breast 2WW"),
            _ref("2024-04-25", concept="suspected lung cancer"),
        ]
        diags = [_diag("2024-05-01", concept="breast carcinoma")]
        closed, _open = _build_diagnosis_led_groups(refs, diags)
        assert len(closed) == 1
        _site, ref_anchors, _diags, method = closed[0]
        assert method == "strict_site"
        assert ref_anchors[0]["encounter_date"] == "2024-03-01"

    def test_idempotent_second_call(self):
        """VT-137-TC-009: running the grouper twice on the same inputs
        returns identical structure (no state leaks)."""
        refs = [_ref("2024-04-10", concept="suspected lung cancer")]
        diags = [_diag("2024-05-01", concept="breast carcinoma")]
        a = _build_diagnosis_led_groups(refs, diags)
        b = _build_diagnosis_led_groups(refs, diags)
        assert a == b
