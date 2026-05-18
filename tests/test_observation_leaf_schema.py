"""Phase 5f -- ObservationLeaf wire-shape validation tests.

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    VT: VT-404C1E2C

Covers the structural rules the Pydantic ObservationLeaf model enforces:

  - operator + value compatibility (between -> [low, high]; rest -> scalar)
  - mutually exclusive evaluation modes
  - within_days envelope enforcement (trend window, temporal interval span)
  - extra="forbid" guard against typos
  - LogicNode dispatch into the OBSERVATION branch and observable_id
    registration in the concept-id pre-flight set
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.guidance_schema.observation_leaf import (
    AggregateSpec,
    ObservationLeaf,
    ObservationLeafValidationError,
    ReferenceRangeSpec,
    TemporalSpec,
    TrendSpec,
)
from services.api.app.services.guidance_rule_edit import (
    LogicNode,
    LogicTreeValidationError,
    validate_logic_tree,
)


# ---------------------------------------------------------------------------
# ObservationLeaf -- happy paths
# ---------------------------------------------------------------------------


def test_absolute_mode_round_trips() -> None:
    leaf = ObservationLeaf(
        observable_id="365632008",
        operator=">=",
        value=400.0,
        unit="10*9/L",
    )
    assert leaf.mode() == "absolute"
    assert leaf.value == 400.0
    assert leaf.within_days == 365


def test_between_operator_coerces_pair() -> None:
    leaf = ObservationLeaf(
        observable_id="60621009",
        operator="between",
        value=[18.5, 25.0],
        unit="kg/m2",
    )
    assert leaf.value == (18.5, 25.0)


def test_temporal_mode_carries_pattern() -> None:
    leaf = ObservationLeaf(
        observable_id="313730000",
        operator=">=",
        value=4.0,
        unit="ug/L",
        within_days=730,
        temporal=TemporalSpec(
            count=2,
            interval_min_days=180,
            interval_max_days=540,
        ),
    )
    assert leaf.mode() == "temporal"
    assert leaf.temporal is not None
    assert leaf.temporal.count == 2


def test_reference_range_mode() -> None:
    leaf = ObservationLeaf(
        observable_id="45896005",
        operator=">",
        value=1.0,
        unit="U/L",
        reference_range=ReferenceRangeSpec(bound="upper", multiple_of_range=3.0),
    )
    assert leaf.mode() == "reference_range"


def test_trend_mode_with_percent_delta() -> None:
    leaf = ObservationLeaf(
        observable_id="1011481000000105",
        operator="<=",
        value=-25.0,
        unit="mL/min/{1.73_m2}",
        within_days=365,
        trend=TrendSpec(delta_kind="percent", window_days=365),
    )
    assert leaf.mode() == "trend"


def test_aggregate_mode_mean_of_three() -> None:
    leaf = ObservationLeaf(
        observable_id="1003671000000109",
        operator=">=",
        value=64.0,
        unit="mmol/mol",
        aggregation=AggregateSpec(kind="mean", lookback_n=3),
    )
    assert leaf.mode() == "aggregate"


# ---------------------------------------------------------------------------
# ObservationLeaf -- sad paths
# ---------------------------------------------------------------------------


_OBS_VALIDATION = (ValidationError, ObservationLeafValidationError)


def test_between_without_pair_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="60621009",
            operator="between",
            value=22.0,  # scalar instead of [low, high]
            unit="kg/m2",
        )


def test_between_with_inverted_bounds_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="60621009",
            operator="between",
            value=[30.0, 18.5],
            unit="kg/m2",
        )


def test_scalar_operator_with_list_value_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="365632008",
            operator=">=",
            value=[400.0, 500.0],  # not allowed for >=
            unit="10*9/L",
        )


def test_two_modes_at_once_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="365632008",
            operator=">=",
            value=400.0,
            unit="10*9/L",
            temporal=TemporalSpec(count=2, interval_min_days=30),
            aggregation=AggregateSpec(kind="mean", lookback_n=3),
        )


def test_trend_window_outside_within_days_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="1011481000000105",
            operator="<=",
            value=-25.0,
            unit="mL/min/{1.73_m2}",
            within_days=180,
            trend=TrendSpec(delta_kind="percent", window_days=365),
        )


def test_temporal_pattern_outside_envelope_raises() -> None:
    # Three readings spaced >= 200 days apart need 400 days minimum,
    # which exceeds within_days=365.
    with pytest.raises(_OBS_VALIDATION):
        ObservationLeaf(
            observable_id="313730000",
            operator=">=",
            value=4.0,
            unit="ug/L",
            within_days=365,
            temporal=TemporalSpec(count=3, interval_min_days=200),
        )


def test_extra_keys_are_rejected() -> None:
    with pytest.raises(Exception):
        ObservationLeaf(
            observable_id="365632008",
            operator=">=",
            value=400.0,
            unit="10*9/L",
            wibble=True,  # type: ignore[call-arg]
        )


def test_temporal_interval_max_below_min_raises() -> None:
    with pytest.raises(_OBS_VALIDATION):
        TemporalSpec(count=2, interval_min_days=180, interval_max_days=90)


# ---------------------------------------------------------------------------
# LogicNode dispatch into the OBSERVATION branch
# ---------------------------------------------------------------------------


def test_logic_tree_accepts_observation_leaf() -> None:
    node = LogicNode(
        kind="OBSERVATION",
        node_id="obs_1",
        observation=ObservationLeaf(
            observable_id="365632008",
            operator=">=",
            value=400.0,
            unit="10*9/L",
        ),
    )
    concept_ids = validate_logic_tree(node)
    assert concept_ids == {"365632008"}


def test_logic_tree_rejects_observation_without_payload() -> None:
    node = LogicNode(kind="OBSERVATION", node_id="obs_1")
    with pytest.raises(LogicTreeValidationError):
        validate_logic_tree(node)


def test_logic_tree_unknown_kind_still_rejected() -> None:
    with pytest.raises(ValueError):
        LogicNode(kind="MYSTERY", node_id="x")
