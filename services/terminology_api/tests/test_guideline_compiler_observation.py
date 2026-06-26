"""Phase 5f -- compiler echo tests for the OBSERVATION leaf.

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    VT: VT-404C1E2C

The compiler does NOT evaluate the leaf; it only:

  - rejects leaves that reference an unknown observable (drops the
    rule, fails closed);
  - rejects leaves whose authored unit cannot be reconciled with the
    canonical unit (drops the rule, fails closed);
  - canonicalises the threshold value(s) into the canonical unit so
    the evaluator never has to negotiate units at fire time;
  - echoes the leaf's structure (mode-specific sub-specs, recency
    window) into the compiled tree so the evaluator can dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_compiler import (
    CompilePolicy,
    GuidelineCompiler,
)


@pytest.fixture()
def compiler() -> GuidelineCompiler:
    store = MagicMock(spec=BitmapStore)
    return GuidelineCompiler(store=store)


def _policy() -> CompilePolicy:
    return CompilePolicy(
        mode="advisory",
        allowed_concept_ids=set(),
        enforce_action_scope=False,
    )


_NO_KG = patch(
    "services.terminology_api.app.services.guideline_compiler.get_lab_config",
    return_value=None,
)


@_NO_KG
def test_empty_unit_defaults_to_canonical_unit(
    _mock_lab, compiler: GuidelineCompiler
) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_no_unit",
        "observable_id": "365632008",
        "operator": ">=",
        "value": 400.0,
        "unit": "",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["wire_unit"] == "10*9/L"
    assert out["value"] == 400.0


@_NO_KG
def test_compiles_absolute_leaf_in_canonical_unit(
    _mock_lab, compiler: GuidelineCompiler
) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_1",
        "observable_id": "365632008",
        "observable_term": "Platelet count",
        "operator": ">=",
        "value": 400.0,
        "unit": "10*9/L",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["kind"] == "observation"
    assert out["observable_id"] == "365632008"
    assert out["operator"] == ">="
    assert out["value"] == 400.0
    assert out["unit"] == "10*9/L"
    assert out["wire_unit"] == "10*9/L"
    assert out["within_days"] == 365
    assert out["temporal"] is None
    assert out["reference_range"] is None
    assert out["trend"] is None
    assert out["aggregation"] is None


def test_canonicalises_threshold_when_authored_in_alias_unit(
    compiler: GuidelineCompiler,
) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_creat",
        "observable_id": "113075003",
        "operator": ">",
        "value": 1.5,
        "unit": "mg/dL",
        "within_days": 90,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    # 1.5 mg/dL * 88.4 = 132.6 umol/L (canonical).
    assert out["value"] == pytest.approx(132.6, abs=1e-3)
    assert out["unit"] == "umol/L"
    assert out["wire_unit"] == "mg/dL"


def test_canonicalises_between_pair(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_bmi",
        "observable_id": "60621009",
        "operator": "between",
        "value": [18.5, 25.0],
        "unit": "kg/m2",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["value"] == [18.5, 25.0]


def test_unknown_observable_without_unit_drops_rule(
    compiler: GuidelineCompiler,
) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_unknown",
        "observable_id": "9999999999",
        "operator": ">=",
        "value": 1.0,
        "unit": "",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is None


def test_unknown_observable_with_authored_unit_compiles(
    compiler: GuidelineCompiler,
) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_fit",
        "observable_id": "1049361000000101",
        "operator": ">=",
        "value": 10.0,
        "unit": "ug/g",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["observable_id"] == "1049361000000101"
    assert out["value"] == 10.0
    assert out["unit"] == "ug/g"


def test_unparseable_unit_drops_rule(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_bad_unit",
        "observable_id": "365632008",
        "operator": ">=",
        "value": 400.0,
        "unit": "potatoes",
        "within_days": 365,
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is None


def test_missing_observable_id_drops_rule(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_no_id",
        "operator": ">=",
        "value": 400.0,
        "unit": "10*9/L",
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is None


def test_echoes_temporal_specification(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_psa_pattern",
        "observable_id": "313730000",
        "operator": ">=",
        "value": 4.0,
        "unit": "ug/L",
        "within_days": 730,
        "temporal": {
            "count": 2,
            "interval_min_days": 180,
            "interval_max_days": 540,
        },
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["temporal"] == {
        "count": 2,
        "interval_min_days": 180,
        "interval_max_days": 540,
    }


def test_echoes_trend_specification(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_egfr_fall",
        "observable_id": "1011481000000105",
        "operator": "<=",
        "value": -25.0,
        "unit": "mL/min/{1.73_m2}",
        "within_days": 365,
        "trend": {"delta_kind": "percent", "window_days": 365},
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["trend"] == {"delta_kind": "percent", "window_days": 365}


def test_echoes_aggregation_specification(compiler: GuidelineCompiler) -> None:
    leaf = {
        "kind": "observation",
        "node_id": "obs_hba1c_mean",
        "observable_id": "1003671000000109",
        "operator": ">=",
        "value": 64.0,
        "unit": "mmol/mol",
        "within_days": 365,
        "aggregation": {"kind": "mean", "lookback_n": 3},
    }
    out = compiler._compile_logic_tree_node(leaf, session=None, policy=_policy())
    assert out is not None
    assert out["aggregation"] == {"kind": "mean", "lookback_n": 3}


def test_observation_inside_and_tree(compiler: GuidelineCompiler) -> None:
    tree = {
        "kind": "AND",
        "node_id": "root",
        "children": [
            {
                "kind": "DEMOGRAPHIC",
                "node_id": "age_gate",
                "field": "age",
                "operator": ">=",
                "value": 50.0,
            },
            {
                "kind": "observation",
                "node_id": "obs_bmi",
                "observable_id": "60621009",
                "operator": ">=",
                "value": 30.0,
                "unit": "kg/m2",
                "within_days": 365,
            },
        ],
    }
    out = compiler._compile_logic_tree_node(tree, session=None, policy=_policy())
    assert out is not None
    assert out["kind"] == "AND"
    assert len(out["children"]) == 2
    obs = out["children"][1]
    assert obs["kind"] == "observation"
    assert obs["value"] == 30.0


def test_observation_unknown_unit_inside_and_drops_whole_tree(
    compiler: GuidelineCompiler,
) -> None:
    tree = {
        "kind": "AND",
        "node_id": "root",
        "children": [
            {
                "kind": "DEMOGRAPHIC",
                "node_id": "age_gate",
                "field": "age",
                "operator": ">=",
                "value": 50.0,
            },
            {
                "kind": "observation",
                "node_id": "bad",
                "observable_id": "365632008",
                "operator": ">=",
                "value": 400.0,
                "unit": "potatoes",
            },
        ],
    }
    out = compiler._compile_logic_tree_node(tree, session=None, policy=_policy())
    assert out is None
