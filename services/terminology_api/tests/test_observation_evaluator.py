"""Phase 5f -- evaluator tests for the OBSERVATION leaf (5 modes x happy/sad).

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    VT: VT-404C1E2C

Every mode has at least one happy-path test (rule fires when the
patient meets the condition) and at least one fail-closed test (rule
does NOT fire when the data is missing, malformed, or the threshold is
not met). Time-sensitive tests pin ``now`` to a fixed instant so the
recency window is deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.terminology_api.app.services.observation_evaluator import (
    observation_matches,
)


_NOW = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


def _platelet_leaf(**overrides: object) -> dict:
    leaf = {
        "kind": "observation",
        "node_id": "obs_plt",
        "observable_id": "365632008",
        "operator": ">=",
        "value": 400.0,
        "unit": "10*9/L",
        "wire_unit": "10*9/L",
        "within_days": 365,
        "temporal": None,
        "reference_range": None,
        "trend": None,
        "aggregation": None,
    }
    leaf.update(overrides)
    return leaf


def _reading(value: float, days_ago: int, unit: str = "10*9/L") -> dict:
    return {
        "observable_id": "365632008",
        "value": value,
        "unit": unit,
        "observed_at": (_NOW - timedelta(days=days_ago)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Mode 1 -- ABSOLUTE
# ---------------------------------------------------------------------------


def test_absolute_fires_when_latest_meets_threshold() -> None:
    leaf = _platelet_leaf()
    obs = [_reading(482.0, days_ago=10), _reading(350.0, days_ago=200)]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=60.0, now=_NOW)


def test_absolute_does_not_fire_when_latest_below_threshold() -> None:
    leaf = _platelet_leaf()
    obs = [_reading(220.0, days_ago=10)]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=60.0, now=_NOW
    )


def test_absolute_fails_closed_when_no_observations() -> None:
    leaf = _platelet_leaf()
    assert not observation_matches(
        leaf, None, patient_sex="male", patient_age=60.0, now=_NOW
    )
    assert not observation_matches(
        leaf, [], patient_sex="male", patient_age=60.0, now=_NOW
    )


def test_absolute_drops_readings_outside_recency_window() -> None:
    leaf = _platelet_leaf(within_days=30)
    obs = [_reading(482.0, days_ago=200)]  # too old
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=60.0, now=_NOW
    )


def test_absolute_canonicalises_patient_unit() -> None:
    leaf = _platelet_leaf()
    obs = [
        {
            "observable_id": "365632008",
            "value": 0.482,
            "unit": "/nL",  # alias for 10*9/L identity
            "observed_at": (_NOW - timedelta(days=5)).isoformat(),
        }
    ]
    # 0.482 /nL == 0.482 x10*9/L which is BELOW 400; should not fire.
    assert not observation_matches(leaf, obs, patient_sex="male", patient_age=60, now=_NOW)


def test_absolute_between_operator() -> None:
    leaf = _platelet_leaf(operator="between", value=[150.0, 400.0])
    obs = [_reading(280.0, days_ago=5)]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=60, now=_NOW)
    leaf2 = _platelet_leaf(operator="between", value=[150.0, 400.0])
    obs2 = [_reading(50.0, days_ago=5)]
    assert not observation_matches(
        leaf2, obs2, patient_sex="male", patient_age=60, now=_NOW
    )


# ---------------------------------------------------------------------------
# Mode 2 -- TEMPORAL (N consecutive readings, D days apart)
# ---------------------------------------------------------------------------


def _psa_leaf(**overrides: object) -> dict:
    leaf = {
        "kind": "observation",
        "node_id": "obs_psa",
        "observable_id": "313730000",
        "operator": ">=",
        "value": 4.0,
        "unit": "ug/L",
        "wire_unit": "ug/L",
        "within_days": 730,
        "temporal": None,
        "reference_range": None,
        "trend": None,
        "aggregation": None,
    }
    leaf.update(overrides)
    return leaf


def _psa_reading(value: float, days_ago: int) -> dict:
    return {
        "observable_id": "313730000",
        "value": value,
        "unit": "ug/L",
        "observed_at": (_NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_temporal_fires_with_two_consecutive_qualifying_readings() -> None:
    leaf = _psa_leaf(
        temporal={"count": 2, "interval_min_days": 180, "interval_max_days": 540}
    )
    obs = [_psa_reading(5.2, days_ago=30), _psa_reading(4.8, days_ago=240)]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=68, now=_NOW)


def test_temporal_does_not_fire_when_interval_too_short() -> None:
    leaf = _psa_leaf(
        temporal={"count": 2, "interval_min_days": 180, "interval_max_days": 540}
    )
    obs = [_psa_reading(5.2, days_ago=30), _psa_reading(4.8, days_ago=60)]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=68, now=_NOW
    )


def test_temporal_does_not_fire_when_only_one_qualifying() -> None:
    leaf = _psa_leaf(
        temporal={"count": 2, "interval_min_days": 180, "interval_max_days": 540}
    )
    obs = [_psa_reading(5.2, days_ago=30), _psa_reading(2.5, days_ago=240)]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=68, now=_NOW
    )


def test_temporal_fails_closed_with_no_observations() -> None:
    leaf = _psa_leaf(
        temporal={"count": 2, "interval_min_days": 180, "interval_max_days": 540}
    )
    assert not observation_matches(
        leaf, [], patient_sex="male", patient_age=68, now=_NOW
    )


# ---------------------------------------------------------------------------
# Mode 3 -- REFERENCE_RANGE (compare to ULN/LLN)
# ---------------------------------------------------------------------------


def _alt_leaf(**overrides: object) -> dict:
    leaf = {
        "kind": "observation",
        "node_id": "obs_alt",
        "observable_id": "45896005",
        "operator": ">",
        "value": 1.0,  # multiplier handled by reference_range.multiple_of_range
        "unit": "U/L",
        "wire_unit": "U/L",
        "within_days": 90,
        "temporal": None,
        "reference_range": None,
        "trend": None,
        "aggregation": None,
    }
    leaf.update(overrides)
    return leaf


def _alt_reading(value: float, days_ago: int) -> dict:
    return {
        "observable_id": "45896005",
        "value": value,
        "unit": "U/L",
        "observed_at": (_NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_reference_range_fires_when_above_3x_uln_male() -> None:
    leaf = _alt_leaf(
        operator=">",
        value=120.0,  # 3 * 40 (male ULN)
        reference_range={"bound": "upper", "multiple_of_range": 3.0},
    )
    obs = [_alt_reading(150.0, days_ago=10)]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=45, now=_NOW)


def test_reference_range_does_not_fire_when_below_threshold() -> None:
    leaf = _alt_leaf(
        operator=">",
        value=120.0,
        reference_range={"bound": "upper", "multiple_of_range": 3.0},
    )
    obs = [_alt_reading(80.0, days_ago=10)]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=45, now=_NOW
    )


def test_reference_range_fails_closed_when_no_band_for_demographic() -> None:
    leaf = _psa_leaf(
        reference_range={"bound": "upper", "multiple_of_range": 1.0},
    )
    obs = [_psa_reading(10.0, days_ago=10)]
    # PSA bands are male-only; female patient -> no band -> fail closed.
    assert not observation_matches(
        leaf, obs, patient_sex="female", patient_age=68, now=_NOW
    )


def test_reference_range_fails_closed_when_no_readings() -> None:
    leaf = _alt_leaf(
        reference_range={"bound": "upper", "multiple_of_range": 1.0},
    )
    assert not observation_matches(
        leaf, [], patient_sex="male", patient_age=45, now=_NOW
    )


# ---------------------------------------------------------------------------
# Mode 4 -- TREND (delta over window)
# ---------------------------------------------------------------------------


def _egfr_leaf(**overrides: object) -> dict:
    leaf = {
        "kind": "observation",
        "node_id": "obs_egfr",
        "observable_id": "1011481000000105",
        "operator": "<=",
        "value": -25.0,
        "unit": "mL/min/{1.73_m2}",
        "wire_unit": "mL/min/{1.73_m2}",
        "within_days": 365,
        "temporal": None,
        "reference_range": None,
        "trend": {"delta_kind": "percent", "window_days": 365},
        "aggregation": None,
    }
    leaf.update(overrides)
    return leaf


def _egfr_reading(value: float, days_ago: int) -> dict:
    return {
        "observable_id": "1011481000000105",
        "value": value,
        "unit": "mL/min/{1.73_m2}",
        "observed_at": (_NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_trend_percent_fires_on_25pct_fall() -> None:
    leaf = _egfr_leaf()
    obs = [_egfr_reading(60.0, days_ago=10), _egfr_reading(85.0, days_ago=350)]
    # delta = 100*(60-85)/85 = -29.4% which satisfies <= -25%.
    assert observation_matches(leaf, obs, patient_sex="female", patient_age=70, now=_NOW)


def test_trend_percent_does_not_fire_when_drop_too_small() -> None:
    leaf = _egfr_leaf()
    obs = [_egfr_reading(78.0, days_ago=10), _egfr_reading(85.0, days_ago=350)]
    assert not observation_matches(
        leaf, obs, patient_sex="female", patient_age=70, now=_NOW
    )


def test_trend_fails_closed_when_only_one_reading_in_window() -> None:
    leaf = _egfr_leaf()
    obs = [_egfr_reading(60.0, days_ago=10)]
    assert not observation_matches(
        leaf, obs, patient_sex="female", patient_age=70, now=_NOW
    )


def test_trend_absolute_fires_on_drop() -> None:
    leaf = _egfr_leaf(trend={"delta_kind": "absolute", "window_days": 365}, value=-20.0)
    obs = [_egfr_reading(50.0, days_ago=10), _egfr_reading(85.0, days_ago=350)]
    # delta = 50 - 85 = -35.0 which satisfies <= -20.
    assert observation_matches(leaf, obs, patient_sex="female", patient_age=70, now=_NOW)


def test_trend_percent_fails_closed_when_baseline_zero() -> None:
    leaf = _egfr_leaf()
    obs = [_egfr_reading(0.0, days_ago=350), _egfr_reading(60.0, days_ago=10)]
    assert not observation_matches(
        leaf, obs, patient_sex="female", patient_age=70, now=_NOW
    )


# ---------------------------------------------------------------------------
# Mode 5 -- AGGREGATE (mean / median / min / max of last N readings)
# ---------------------------------------------------------------------------


def _hba1c_leaf(**overrides: object) -> dict:
    leaf = {
        "kind": "observation",
        "node_id": "obs_hba1c",
        "observable_id": "1003671000000109",
        "operator": ">=",
        "value": 64.0,
        "unit": "mmol/mol",
        "wire_unit": "mmol/mol",
        "within_days": 365,
        "temporal": None,
        "reference_range": None,
        "trend": None,
        "aggregation": {"kind": "mean", "lookback_n": 3},
    }
    leaf.update(overrides)
    return leaf


def _hba1c_reading(value: float, days_ago: int) -> dict:
    return {
        "observable_id": "1003671000000109",
        "value": value,
        "unit": "mmol/mol",
        "observed_at": (_NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_aggregate_mean_fires_when_average_meets_threshold() -> None:
    leaf = _hba1c_leaf()
    obs = [
        _hba1c_reading(70.0, days_ago=10),
        _hba1c_reading(66.0, days_ago=120),
        _hba1c_reading(60.0, days_ago=240),
    ]
    # mean = 65.33 >= 64
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=55, now=_NOW)


def test_aggregate_mean_does_not_fire_when_average_too_low() -> None:
    leaf = _hba1c_leaf()
    obs = [
        _hba1c_reading(55.0, days_ago=10),
        _hba1c_reading(58.0, days_ago=120),
        _hba1c_reading(50.0, days_ago=240),
    ]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=55, now=_NOW
    )


def test_aggregate_fails_closed_when_fewer_than_lookback_n() -> None:
    leaf = _hba1c_leaf()
    obs = [_hba1c_reading(80.0, days_ago=10)]  # only 1 reading
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=55, now=_NOW
    )


def test_aggregate_max_fires_when_one_reading_exceeds_threshold() -> None:
    leaf = _hba1c_leaf(aggregation={"kind": "max", "lookback_n": 3})
    obs = [
        _hba1c_reading(50.0, days_ago=10),
        _hba1c_reading(72.0, days_ago=120),
        _hba1c_reading(50.0, days_ago=240),
    ]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=55, now=_NOW)


def test_aggregate_median_uses_middle_value() -> None:
    leaf = _hba1c_leaf(aggregation={"kind": "median", "lookback_n": 3})
    obs = [
        _hba1c_reading(40.0, days_ago=10),
        _hba1c_reading(64.0, days_ago=120),
        _hba1c_reading(80.0, days_ago=240),
    ]
    assert observation_matches(leaf, obs, patient_sex="male", patient_age=55, now=_NOW)


# ---------------------------------------------------------------------------
# Cross-mode -- bad-data tolerance
# ---------------------------------------------------------------------------


def test_unparseable_observed_at_is_dropped() -> None:
    leaf = _platelet_leaf()
    obs = [
        {
            "observable_id": "365632008",
            "value": 482,
            "unit": "10*9/L",
            "observed_at": "tomorrow",
        }
    ]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=60, now=_NOW
    )


def test_unknown_unit_in_observation_is_dropped() -> None:
    leaf = _platelet_leaf()
    obs = [
        {
            "observable_id": "365632008",
            "value": 482,
            "unit": "potatoes",
            "observed_at": (_NOW - timedelta(days=10)).isoformat(),
        }
    ]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=60, now=_NOW
    )


def test_observation_for_other_observable_is_ignored() -> None:
    leaf = _platelet_leaf()
    obs = [
        {
            "observable_id": "271026005",  # haemoglobin, not platelets
            "value": 600,
            "unit": "g/L",
            "observed_at": (_NOW - timedelta(days=10)).isoformat(),
        }
    ]
    assert not observation_matches(
        leaf, obs, patient_sex="male", patient_age=60, now=_NOW
    )


def test_missing_observable_id_in_leaf_fails_closed() -> None:
    leaf = _platelet_leaf()
    leaf["observable_id"] = ""
    assert not observation_matches(
        leaf, [_reading(500.0, 5)], patient_sex="male", patient_age=60, now=_NOW
    )
