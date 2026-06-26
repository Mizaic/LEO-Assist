"""NG12 bitmap evaluation scenarios -- golden-set tests.

SNOMED IDs, surface forms, and compiled rule structures are derived from
the knowledge graph snapshot at 2026-05-12.

Active NG12 rules tested (3):
  - rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59
    (1.1.5 mesothelioma urgent CXR)
  - rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725
    (1.3.3 FIT safety netting)
  - rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c
    (1.3.5 rectal mass colorectal referral)

Pending rules (22) are not compiled into the active bitmap and are
therefore not tested here. Add them when they are promoted to active.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

import pytest
from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator

_FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "ng12_test_scenarios.json"
)

# ---------------------------------------------------------------------------
# SNOMED concept ID -> integer ID mapping (test-only; matches compiled order)
# ---------------------------------------------------------------------------
_INT_IDS: dict[str, int] = {
    "49727002": 1,          # Cough (finding)
    "84229001": 2,          # Fatigue (finding)
    "267036007": 3,         # Dyspnea (finding)
    "29857009": 4,          # Chest pain (finding)
    "262285001": 5,         # Weight decreased (finding)
    "79890006": 6,          # Loss of appetite (finding)
    "77176002": 7,          # Smoker (finding)
    "8517006": 8,           # Ex-smoker (finding)
    "161635002": 9,         # History of asbestos exposure (situation)
    "233639007": 10,        # Benign asbestos pleural effusion (disorder)
    "248523006": 11,        # Rectal mass (finding)
    "149441000000102": 12,  # FIT kit declined (situation)
    "1101391000000109": 13, # FIT sample rejected (finding)
    "1101381000000107": 14, # FIT technical failure (finding)
    "1101401000000107": 15, # FIT no response (finding)
    "384241000000100": 16,  # FIT incomplete participation (finding)
    "167667006": 17,        # Occult blood not detected (finding)
}

# Bitmaps for each concept group used in the compiled rules
_BITMAPS: dict[str, BitMap] = {
    "bm_cough": BitMap([1]),
    "bm_fatigue": BitMap([2]),
    "bm_dyspnoea": BitMap([3]),
    "bm_chest_pain": BitMap([4]),
    "bm_weight_loss": BitMap([5]),
    "bm_appetite_loss": BitMap([6]),
    # Smoker seeds: both smoker + ex-smoker in one bitmap (union of seeds)
    "bm_smoker": BitMap([7, 8]),
    # Asbestos seeds: exposure + pleural effusion descendant
    "bm_asbestos": BitMap([9, 10]),
    "bm_rectal_mass": BitMap([11]),
    # FIT safety netting: union of all FIT-related declined/failed codes
    "bm_fit_declined": BitMap([12, 13, 14, 15, 16, 17]),
}


# ---------------------------------------------------------------------------
# Compiled rule builders (mirror what GuidelineCompiler produces at runtime)
# ---------------------------------------------------------------------------

def _concept_node(term: str, snomed_id: str, bitmap_id: str,
                  seed_ids: list[str] | None = None) -> dict:
    """Build a compiled concept leaf node."""
    return {
        "kind": "concept",
        "bitmap_id": bitmap_id,
        "criterion": {
            "term": term,
            "snomed_concept_id": snomed_id,
            "preferred_term": term,
            "semantic_tag": "finding",
        },
        "seed_concept_ids": seed_ids or [snomed_id],
    }


def _symptom_nodes() -> list[dict]:
    """Six shared respiratory/constitutional symptom concept nodes."""
    return [
        _concept_node("cough", "49727002", "bm_cough"),
        _concept_node("fatigue", "84229001", "bm_fatigue"),
        _concept_node("dyspnoea", "267036007", "bm_dyspnoea"),
        _concept_node("chest pain", "29857009", "bm_chest_pain"),
        _concept_node("weight loss", "262285001", "bm_weight_loss"),
        _concept_node("loss of appetite", "79890006", "bm_appetite_loss"),
    ]


def _build_mesothelioma_rule() -> dict:
    """Compile the active mesothelioma urgent CXR rule (1.1.5)."""
    symptoms = _symptom_nodes()
    return {
        "rule_id": (
            "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13"
            ":edit:dd11e8d3:edit:a0b74f59"
        ),
        "name": "1.1.5 Offer urgent chest X-ray for mesothelioma",
        "strength": "offer",
        "schema_version": 2,
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "chapter_title": "Recommendations organised by site of cancer",
        "recommendation_verbatim": (
            "Offer an urgent chest X-ray (within 2 weeks) to assess for "
            "mesothelioma in people aged 40 and over."
        ),
        "logic_tree": {
            "kind": "AND",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": ">=",
                    "value": 40.0,
                    "unit": "years",
                },
                {
                    "kind": "OR",
                    "children": [
                        {
                            "kind": "AT_LEAST",
                            "min": 2,
                            "children": symptoms,
                        },
                        {
                            "kind": "AND",
                            "children": [
                                _concept_node(
                                    "smoker", "77176002", "bm_smoker",
                                    seed_ids=["77176002", "8517006"],
                                ),
                                {"kind": "AT_LEAST", "min": 1,
                                 "children": symptoms},
                            ],
                        },
                        {
                            "kind": "AND",
                            "children": [
                                _concept_node(
                                    "asbestos exposure", "161635002",
                                    "bm_asbestos",
                                    seed_ids=["161635002", "233639007"],
                                ),
                                {"kind": "AT_LEAST", "min": 1,
                                 "children": symptoms},
                            ],
                        },
                    ],
                },
            ],
        },
        "action": None,
        "applies_to": [],
        "criteria_groups": [],
    }


def _build_fit_safety_netting_rule() -> dict:
    """Compile the active FIT safety netting rule (1.3.3)."""
    return {
        "rule_id": "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725",
        "name": "1.3.3 Cancer Safety Netting",
        "strength": "safety_net",
        "schema_version": 2,
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "chapter_title": "Recommendations organised by site of cancer",
        "recommendation_verbatim": (
            "Safety netting processes should be in place for people who "
            "have not returned a faecal sample or have a FIT result "
            "below 10 micrograms."
        ),
        "logic_tree": {
            "kind": "OR",
            "children": [
                _concept_node(
                    "faecal sample not returned",
                    "149441000000102",
                    "bm_fit_declined",
                    seed_ids=[
                        "149441000000102",
                        "1101391000000109",
                        "1101381000000107",
                        "1101401000000107",
                        "384241000000100",
                        "167667006",
                    ],
                ),
            ],
        },
        "action": None,
        "applies_to": [],
        "criteria_groups": [],
    }


def _build_rectal_mass_rule() -> dict:
    """Compile the active rectal mass colorectal referral rule (1.3.5)."""
    return {
        "rule_id": "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c",
        "name": "1.3.5 Rectal mass suspected colorectal cancer referral",
        "strength": "refer",
        "schema_version": 2,
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "chapter_title": "Recommendations organised by site of cancer",
        "recommendation_verbatim": (
            "Consider a suspected cancer pathway referral for colorectal "
            "cancer in adults with a rectal mass."
        ),
        "logic_tree": {
            "kind": "AND",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": ">=",
                    "value": 18.0,
                    "unit": "years",
                },
                _concept_node("rectal mass", "248523006", "bm_rectal_mass"),
            ],
        },
        "action": None,
        "applies_to": [],
        "criteria_groups": [],
    }


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ng12_ruleset() -> dict:
    """Active NG12 compiled ruleset (3 rules)."""
    return {
        "version": "ng12-test-golden-2026-05-12",
        "compile_timestamp": "2026-05-12T14:00:00Z",
        "scope_type": "guideline",
        "scope_id": "NG12",
        "rules": [
            _build_mesothelioma_rule(),
            _build_fit_safety_netting_rule(),
            _build_rectal_mass_rule(),
        ],
    }


@pytest.fixture()
def evaluator(ng12_ruleset: dict) -> GuidelineEvaluator:
    """GuidelineEvaluator wired to the NG12 test ruleset via mock store."""
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ng12_ruleset
    store.get_ruleset.return_value = ng12_ruleset
    store.get_int_id.side_effect = lambda cid: _INT_IDS.get(cid)
    store.get_bitmap.side_effect = lambda bid: _BITMAPS.get(bid)
    store.get_int_ids_bulk.side_effect = lambda cids: {
        cid: _INT_IDS[cid] for cid in cids if cid in _INT_IDS
    }
    store.get_bitmaps_bulk.side_effect = lambda bids: {
        bid: _BITMAPS[bid] for bid in bids if bid in _BITMAPS
    }
    return GuidelineEvaluator(store=store)


@pytest.fixture()
def scenarios() -> list[dict]:
    """Load bitmap scenarios from the golden fixture file."""
    data = json.loads(_FIXTURE_PATH.read_text())
    return data["bitmap_scenarios"]


# ---------------------------------------------------------------------------
# Parametrised scenario tests
# ---------------------------------------------------------------------------

def _scenario_ids(scenarios: list[dict]) -> list[str]:
    return [s["id"] for s in scenarios]


@pytest.mark.parametrize(
    "scenario",
    json.loads(_FIXTURE_PATH.read_text())["bitmap_scenarios"],
    ids=_scenario_ids(
        json.loads(_FIXTURE_PATH.read_text())["bitmap_scenarios"]
    ),
)
def test_bitmap_scenario(evaluator: GuidelineEvaluator, scenario: dict) -> None:
    """Each scenario's patient codes and age produce the correct fired rules."""
    result = evaluator.evaluate_patient(
        scenario["patient_snomed_codes"],
        patient_age=scenario.get("patient_age"),
        patient_sex=scenario.get("patient_sex"),
        scope_type="guideline",
        scope_id="NG12",
    )

    fired_ids = {r["rule_id"] for r in result["matched_rules"]}
    expected_ids = set(scenario["expected_fired_rule_ids"])
    must_not_ids = set(scenario["must_not_fire_rule_ids"])

    assert expected_ids <= fired_ids, (
        f"{scenario['id']}: expected rules did not fire. "
        f"Expected {expected_ids}, got {fired_ids}"
    )
    overlap = must_not_ids & fired_ids
    assert not overlap, (
        f"{scenario['id']}: rules fired that must not fire: {overlap}"
    )


# ---------------------------------------------------------------------------
# Additional targeted tests for each active rule
# ---------------------------------------------------------------------------

class TestMesotheliomaCXRRule:
    """Rule 1.1.5: age 40+, with (2+ symptoms OR smoker+1 OR asbestos+1)."""

    def test_asbestos_exposure_with_single_symptom_fires(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """Asbestos-exposed patient aged 40+ with one symptom fires the rule."""
        result = evaluator.evaluate_patient(
            ["161635002", "29857009"],  # asbestos exposure + chest pain
            patient_age=62.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59"
            in fired
        )

    def test_single_symptom_non_smoker_no_asbestos_does_not_fire(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """One symptom without smoking or asbestos history must not fire."""
        result = evaluator.evaluate_patient(
            ["49727002"],  # cough only
            patient_age=50.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59"
            not in fired
        )


class TestFITSafetyNettingRule:
    """Rule 1.3.3: any FIT non-return / failure code fires regardless of age."""

    def test_fit_technical_failure_fires(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """FIT sample technical failure code fires safety netting."""
        result = evaluator.evaluate_patient(
            ["1101381000000107"],  # FIT technical failure
            patient_age=58.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725"
            in fired
        )

    def test_no_fit_code_does_not_fire(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """A patient without any FIT code must not trigger safety netting."""
        result = evaluator.evaluate_patient(
            ["49727002", "84229001"],  # respiratory symptoms, no FIT code
            patient_age=60.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725"
            not in fired
        )


class TestRectalMassRule:
    """Rule 1.3.5: adult (age 18+) with rectal mass."""

    def test_young_adult_with_rectal_mass_fires(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """Rule fires for an 18-year-old (boundary age)."""
        result = evaluator.evaluate_patient(
            ["248523006"],  # rectal mass
            patient_age=18.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c"
            in fired
        )

    def test_minor_with_rectal_mass_does_not_fire(
        self, evaluator: GuidelineEvaluator
    ) -> None:
        """Rule must not fire for a patient under 18."""
        result = evaluator.evaluate_patient(
            ["248523006"],  # rectal mass
            patient_age=16.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        fired = {r["rule_id"] for r in result["matched_rules"]}
        assert (
            "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c"
            not in fired
        )


class TestNoActiveRuleset:
    """Evaluator must handle missing ruleset gracefully."""

    def test_returns_empty_when_no_ruleset(self) -> None:
        """evaluate_patient returns zero matches when store has no ruleset."""
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = None
        ev = GuidelineEvaluator(store=store)
        result = ev.evaluate_patient(
            ["248523006"],
            patient_age=72.0,
            scope_type="guideline",
            scope_id="NG12",
        )
        assert result["matched_rules"] == []
        assert result["active_version"] is None
