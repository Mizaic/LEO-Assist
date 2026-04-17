"""VT-LEO-AI-119 - Referral-to-diagnosis gap guard + PRISM primacy.

Covers TC-001..TC-006.
"""

from __future__ import annotations

import importlib
import os
from datetime import date, timedelta

import pytest


def test_same_day_referral_is_claimed():
    """VT-119-TC-001: DI-LEO-AI-145 -- same-day (d-0) PRISM referral IS claimed.

    MIN_REFERRAL_TO_DIAG_DAYS was reduced from 3 to 0 to support one-stop
    breast/dermatology clinics where the GP completes the PRISM questionnaire
    and the suspected-cancer SNOMED code is entered on the same calendar day.
    """
    from services.analysis_worker.app.analyzers.episode_builder._grouping import (
        _find_best_referral,
    )

    diag = date(2024, 2, 1)
    sorted_ref = [
        {
            "encounter_date": "2024-02-01",
            "concept_id": "276341000000102",
            "concept_name": "breast 2WW",
        }
    ]
    result = _find_best_referral(diag, "breast", sorted_ref, set())
    assert result is not None, (
        "DI-LEO-AI-145: same-day PRISM referral must be claimed (MIN_REFERRAL_TO_DIAG_DAYS=0)"
    )
    idx, ref_date = result
    assert ref_date == date(2024, 2, 1)


def test_earlier_referral_preferred_over_sub_gap_candidate():
    """VT-119-TC-002."""
    from services.analysis_worker.app.analyzers.episode_builder._grouping import (
        _find_best_referral,
    )

    diag = date(2024, 2, 1)
    sorted_ref = [
        {
            "encounter_date": "2024-01-02",
            "concept_id": "276341000000102",
            "concept_name": "breast 2WW",
        },
        {
            "encounter_date": "2024-02-01",
            "concept_id": "276341000000102",
            "concept_name": "breast 2WW note in diagnosis clinic",
        },
    ]
    result = _find_best_referral(diag, "breast", sorted_ref, set())
    assert result is not None
    idx, ref_date = result
    assert idx == 0
    assert ref_date == date(2024, 1, 2)


def test_min_gap_respects_env_override(monkeypatch):
    """VT-119-TC-003."""
    monkeypatch.setenv("EPISODE_MIN_REFERRAL_TO_DIAG_DAYS", "7")

    from services.analysis_worker.app.analyzers.episode_builder import _config as cfg

    reloaded = importlib.reload(cfg)
    assert reloaded.MIN_REFERRAL_TO_DIAG_DAYS == 7

    # DI-LEO-AI-145: default changed from 3 to 0; restore to new default
    monkeypatch.setenv("EPISODE_MIN_REFERRAL_TO_DIAG_DAYS", "0")
    importlib.reload(cfg)


def test_prism_regex_matches_finalised_phrasing():
    """VT-119-TC-004."""
    from services.analysis_worker.app.analyzers.anchor_detector import (
        _RE_REFERRAL_PRISM,
    )

    positive = [
        "PRISM 2WW questionnaire finalised",
        "PRISM questionnaire submitted today",
        "PRISM proforma completed and sent",
        "2WW proforma finalised",
        "PRISM form issued",
    ]
    negative = [
        "plan to refer 2WW",
        "fast-track referral next week",
        "PRISM entered in record",
    ]
    for text in positive:
        assert _RE_REFERRAL_PRISM.search(text), f"PRISM should match: {text!r}"
    for text in negative:
        assert not _RE_REFERRAL_PRISM.search(text), f"PRISM must not match: {text!r}"


def _classify_one_encounter(text: str, enc_id: str = "E1") -> list[dict]:
    """Helper: run _classify_text_encounters on a single synthetic row."""
    from services.analysis_worker.app.analyzers.anchor_detector import (
        _classify_text_encounters,
    )

    rows = [
        {
            "encounter_id": enc_id,
            "encounter_date": "2024-01-10",
            "text": text,
            "content_type": "consultation",
        }
    ]
    result = _classify_text_encounters(rows, already_coded_ids=set())
    # _classify_text_encounters returns a 7-tuple (referrals first).
    return list(result[0])


def test_prism_primacy_dedupe():
    """VT-119-TC-005: Only one referral anchor emitted when both patterns match."""
    text = "Patient reviewed, plan fast-track referral. PRISM 2WW questionnaire finalised."
    referrals = _classify_one_encounter(text)
    assert len(referrals) == 1
    assert referrals[0]["referral_subtype"] == "prism"
    assert referrals[0]["confidence"] == 0.9


def test_generic_referral_retains_text_generic_label():
    """VT-119-TC-006."""
    text = "Plan urgent cancer referral fast-track."
    referrals = _classify_one_encounter(text)
    assert len(referrals) == 1
    assert referrals[0]["referral_subtype"] == "text_generic"
    assert referrals[0]["confidence"] == 0.6


def test_no_referral_when_neither_matches():
    """Control: neither regex match -> no referral anchor."""
    text = "Annual health check, BP 130/80, no concerns discussed."
    referrals = _classify_one_encounter(text)
    assert len(referrals) == 0


@pytest.mark.parametrize("gap_days", [3, 4, 30, 179])
def test_valid_gap_selected(gap_days):
    """Cross-check: referrals at or above MIN_REFERRAL_TO_DIAG_DAYS are selected."""
    from services.analysis_worker.app.analyzers.episode_builder._grouping import (
        _find_best_referral,
    )

    diag = date(2024, 2, 1)
    ref_date = diag - timedelta(days=gap_days)
    sorted_ref = [
        {
            "encounter_date": ref_date.isoformat(),
            "concept_id": "276341000000102",
            "concept_name": "breast 2WW",
        }
    ]
    result = _find_best_referral(diag, "breast", sorted_ref, set())
    assert result is not None
    assert result[1] == ref_date
