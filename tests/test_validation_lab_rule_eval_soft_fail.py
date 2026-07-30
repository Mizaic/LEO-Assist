"""evaluate_variant_against_rule must not raise when Redis/evaluator fails.

Atlas: DI-EB716E68 / VT-C6B93AF0
"""

from __future__ import annotations

from unittest.mock import MagicMock


def test_evaluate_soft_fails_when_evaluate_patient_raises(monkeypatch) -> None:
    from libs.validation_lab import rule_grounded_eval as mod

    evaluator = MagicMock()
    evaluator._load_ruleset.return_value = {
        "rules": [{"rule_id": "R1"}],
    }
    evaluator.evaluate_patient.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(mod, "_make_evaluator", lambda: evaluator)
    monkeypatch.setattr(mod, "_ruleset_contains_rule", lambda ev, rid: True)

    trigger, reason = mod.evaluate_variant_against_rule(
        "R1",
        {"patientAge": 50, "pmh": [{"conceptId": "123"}]},
    )
    assert trigger is None
    assert reason == "rule not currently compiled"
