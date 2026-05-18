"""Bitmap harness for NG12 GDL rows tied to the three golden active rules.

Non-active rows are excluded from parametrisation here; CI policy and the
stable skip string ``Rule not active in graph`` live in
``tests.helpers.ng12_scenario_policy`` (see ``test_ng12_scenario_policy.py``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator

from tests.helpers.ng12_scenario_loader import load_paired_scenarios
from tests.helpers.ng12_scenario_policy import should_run_bitmap_harness_assertion
from tests.test_ng12_bitmap_scenarios import (
    _BITMAPS,
    _INT_IDS,
    _build_fit_safety_netting_rule,
    _build_mesothelioma_rule,
    _build_rectal_mass_rule,
)

RECT_RULE = "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c"


def _ruleset() -> dict:
    return {
        "version": "ng12-scenario-harness",
        "compile_timestamp": "2026-05-12T14:00:00Z",
        "scope_type": "guideline",
        "scope_id": "NG12",
        "rules": [
            _build_mesothelioma_rule(),
            _build_fit_safety_netting_rule(),
            _build_rectal_mass_rule(),
        ],
    }


def _evaluator() -> GuidelineEvaluator:
    rs = _ruleset()
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = rs
    store.get_ruleset.return_value = rs
    store.get_int_id.side_effect = lambda cid: _INT_IDS.get(cid)
    store.get_bitmap.side_effect = lambda bid: _BITMAPS.get(bid)
    return GuidelineEvaluator(store=store)


def _gdl_rows() -> list[dict]:
    gdl, _, _ = load_paired_scenarios()
    return gdl["scenarios"]


_HARNESS_ROWS = [r for r in _gdl_rows() if should_run_bitmap_harness_assertion(r)]


@pytest.mark.parametrize(
    "scenario",
    _HARNESS_ROWS,
    ids=[r["id"] for r in _HARNESS_ROWS],
)
def test_gdl_harness_matches_expectation(scenario: dict) -> None:
    """Active golden rules fire exactly when ``expect_graph_match`` is true."""
    ev = _evaluator()
    res = ev.evaluate_patient(
        scenario["patient_snomed_codes"],
        patient_age=scenario.get("patient_age"),
        patient_sex=scenario.get("patient_sex"),
        scope_type="guideline",
        scope_id="NG12",
    )
    fired = {r["rule_id"] for r in res["matched_rules"]}
    rid = scenario["graph_rule_id"]
    want = scenario["expect_graph_match"] is True
    if want:
        assert rid in fired, f"{scenario['id']}: expected {rid} fired, got {fired}"
    else:
        assert (
            rid not in fired
        ), f"{scenario['id']}: expected {rid} not fired, got {fired}"


def test_harness_covers_three_rules_with_pos_and_neg() -> None:
    """Mesothelioma + FIT have pos/neg rows; rectal has at least one positive."""
    gdl, _, _ = load_paired_scenarios()
    per_rule: dict[str, set[bool]] = {}
    for row in gdl["scenarios"]:
        if not should_run_bitmap_harness_assertion(row):
            continue
        rid = row["graph_rule_id"]
        ex = row["expect_graph_match"]
        per_rule.setdefault(rid, set()).add(bool(ex))
    assert len(per_rule) == 3
    for rid, flags in per_rule.items():
        assert True in flags, f"{rid} missing a positive harness row"
        if rid == RECT_RULE:
            continue
        assert False in flags, f"{rid} missing a negative harness row"
