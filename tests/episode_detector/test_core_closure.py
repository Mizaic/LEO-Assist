"""Hermetic tests for the site-agnostic core closure rules.

Atlas trace:
  DI: DI-FA3CE229 (core closure ships with detector binary, not
      per-site rulebook)
"""

from __future__ import annotations

from datetime import datetime

from libs.episode_detector.core_closure import (
    CORE_CLOSURE_SNOMED,
    DECEASED_SNOMED,
    evaluate_core_closure,
)


NOW = datetime(2026, 4, 22, 12, 0, 0)


def _enc(date: str, codes: tuple[str, ...] = ()) -> dict:
    return {
        "encounter_date": datetime.fromisoformat(date),
        "coded_snomed": list(codes),
    }


def test_no_encounters_returns_keep_open():
    decision = evaluate_core_closure(encounters=[], now=NOW)
    assert decision.should_close is False
    assert decision.status is None


def test_recent_activity_returns_keep_open():
    enc = _enc("2026-04-10")
    decision = evaluate_core_closure(encounters=[enc], now=NOW)
    assert decision.should_close is False


def test_180_day_inactivity_closes_as_inactive():
    enc = _enc("2025-09-01")
    decision = evaluate_core_closure(encounters=[enc], now=NOW)
    assert decision.should_close is True
    assert decision.status == "closed_inactive"
    assert decision.closure_at == datetime(2025, 9, 1)


def test_deceased_snomed_closes_as_deceased():
    snomed = next(iter(DECEASED_SNOMED))
    enc = _enc("2026-03-01", (snomed,))
    decision = evaluate_core_closure(encounters=[enc], now=NOW)
    assert decision.should_close is True
    assert decision.status == "closed_deceased"


def test_discharge_snomed_closes_as_discharged():
    snomed = next(iter(CORE_CLOSURE_SNOMED))
    enc = _enc("2026-03-01", (snomed,))
    decision = evaluate_core_closure(encounters=[enc], now=NOW)
    assert decision.should_close is True
    assert decision.status == "closed_discharged"


def test_deceased_wins_over_discharge():
    deceased = next(iter(DECEASED_SNOMED))
    discharge = next(iter(CORE_CLOSURE_SNOMED))
    encounters = [
        _enc("2026-03-01", (discharge,)),
        _enc("2026-04-01", (deceased,)),
    ]
    decision = evaluate_core_closure(encounters=encounters, now=NOW)
    assert decision.status == "closed_deceased"


def test_iso_string_encounter_date_is_coerced():
    decision = evaluate_core_closure(
        encounters=[{"encounter_date": "2025-09-01", "coded_snomed": []}],
        now=NOW,
    )
    assert decision.should_close is True
    assert decision.status == "closed_inactive"


def test_custom_inactivity_days_threshold():
    enc = _enc("2026-01-01")
    decision = evaluate_core_closure(
        encounters=[enc], now=NOW, inactivity_days=30
    )
    assert decision.should_close is True
    assert decision.status == "closed_inactive"
