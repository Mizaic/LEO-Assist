"""Observable readings need a real observation date, not persist time.

Atlas trace:
  DI: DI-0BB36B4D
  VT: VT-EB54A215
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-0BB36B4D")
"""

from __future__ import annotations

from libs.pipeline.observation_date import parse_observation_date


def test_iso_date_is_kept() -> None:
    assert parse_observation_date("HbA1c 48 mmol/mol 2026-03-12") == "2026-03-12"


def test_uk_day_month_year_words() -> None:
    assert (
        parse_observation_date("Blood Pressure | 140 / 80 mmHg, 24 Nov 2025")
        == "2025-11-24"
    )


def test_dotted_uk_date() -> None:
    assert parse_observation_date("Specimen 23.06.26") == "2026-06-23"


def test_two_different_dates_are_not_guessed() -> None:
    assert parse_observation_date("from 01 Jan 2025 to 24 Nov 2025") is None


def test_missing_date_is_none() -> None:
    assert parse_observation_date("Haemoglobin 118 g/L") is None


def test_reference_range_is_not_a_date() -> None:
    assert parse_observation_date("2.41 10^9/L [1.5 - 7.5]") is None
