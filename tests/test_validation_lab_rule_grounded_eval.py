"""Tests for deterministic expectedTrigger stamping.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch


class _FakeBitMap:
    def __init__(self, values=()):
        self._data: set = set(values)

    def __and__(self, other):
        return _FakeBitMap(self._data & other._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, item):
        return item in self._data

    def issubset(self, other):
        return self._data.issubset(other._data)


_pyroaring_mod = ModuleType("pyroaring")
_pyroaring_mod.BitMap = _FakeBitMap  # type: ignore[attr-defined]
sys.modules.setdefault("pyroaring", _pyroaring_mod)

_redis_mod = ModuleType("redis")
_redis_mod.Redis = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("redis", _redis_mod)

_obs_eval_mod = ModuleType(
    "services.terminology_api.app.services.observation_evaluator"
)
_obs_eval_mod.observation_matches = MagicMock(  # type: ignore[attr-defined]
    return_value=False
)
sys.modules.setdefault(
    "services.terminology_api.app.services.observation_evaluator", _obs_eval_mod
)


def _variant(**overrides: Any) -> dict[str, Any]:
    data = {
        "patientAge": "68",
        "patientSex": "female",
        "pmh": [{"conceptId": "123", "term": "x", "category": "condition"}],
        "triggerConceptIds": ["123"],
        "observations": [],
        "targetRecId": "rec-1",
    }
    data.update(overrides)
    return data


def test_no_rule_id_returns_null_without_evaluator() -> None:
    from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule

    with patch("libs.validation_lab.rule_grounded_eval._make_evaluator") as cls:
        trigger, reason = evaluate_variant_against_rule(None, _variant())
    assert trigger is None
    assert reason == "no recommendation attached"
    cls.assert_not_called()


def test_rule_not_compiled_returns_null_not_false() -> None:
    from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule

    evaluator = MagicMock()
    evaluator.evaluate_patient.return_value = {
        "matched_rules": [],
        "active_version": "v1",
        "not_compiled": False,
    }
    # Ruleset present but does not contain R1
    with (
        patch(
            "libs.validation_lab.rule_grounded_eval._make_evaluator",
            return_value=evaluator,
        ),
        patch(
            "libs.validation_lab.rule_grounded_eval._ruleset_contains_rule",
            return_value=False,
        ),
    ):
        trigger, reason = evaluate_variant_against_rule("R1", _variant())
    assert trigger is None
    assert reason == "rule not currently compiled"


def test_matching_rule_returns_true() -> None:
    from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule

    evaluator = MagicMock()
    evaluator.evaluate_patient.return_value = {
        "matched_rules": [{"rule_id": "R1"}],
        "active_version": "v1",
        "not_compiled": False,
    }
    with (
        patch(
            "libs.validation_lab.rule_grounded_eval._make_evaluator",
            return_value=evaluator,
        ),
        patch(
            "libs.validation_lab.rule_grounded_eval._ruleset_contains_rule",
            return_value=True,
        ),
    ):
        trigger, reason = evaluate_variant_against_rule("R1", _variant())
    assert trigger is True
    assert reason == "verified"


def test_non_matching_rule_returns_false() -> None:
    from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule

    evaluator = MagicMock()
    evaluator.evaluate_patient.return_value = {
        "matched_rules": [{"rule_id": "OTHER"}],
        "active_version": "v1",
        "not_compiled": False,
    }
    with (
        patch(
            "libs.validation_lab.rule_grounded_eval._make_evaluator",
            return_value=evaluator,
        ),
        patch(
            "libs.validation_lab.rule_grounded_eval._ruleset_contains_rule",
            return_value=True,
        ),
    ):
        trigger, reason = evaluate_variant_against_rule("R1", _variant())
    assert trigger is False
    assert reason == "verified"


def test_observations_mapped_to_patient_observations() -> None:
    from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule

    evaluator = MagicMock()
    evaluator.evaluate_patient.return_value = {
        "matched_rules": [],
        "active_version": "v1",
        "not_compiled": False,
    }
    variant = _variant(
        observations=[{"observableId": "100", "value": 50.0, "unit": "U/mL"}]
    )
    with (
        patch(
            "libs.validation_lab.rule_grounded_eval._make_evaluator",
            return_value=evaluator,
        ),
        patch(
            "libs.validation_lab.rule_grounded_eval._ruleset_contains_rule",
            return_value=True,
        ),
    ):
        evaluate_variant_against_rule("R1", variant)
    kwargs = evaluator.evaluate_patient.call_args.kwargs
    obs = kwargs["patient_observations"]
    assert obs[0]["observable_id"] == "100"
    assert obs[0]["value"] == 50.0
    assert obs[0]["unit"] == "U/mL"
    assert "observed_at" in obs[0]
