"""NG12 1.5.2 must not treat vulval pain as pelvic pain.

NHS 4245590920: Vulval pain 162145001 is a SNOMED child of
Pain in pelvis 30473006. That fired ovarian-symptom rule 1.5.2.

Owner: AppropriatenessRule.logicJson excluded_concept_ids on the
Pain in pelvis leaf.

Atlas: DI-185DE0CE, DO-5899D7BE, VT-2082C55B, UN-5F3BF083.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pyroaring import BitMap

from libs.guidelines.ng12_152_pelvic_pain import (
    OVARIAN_PAIN_ID,
    PELVIC_PAIN_ID,
    VULVAL_PAIN_ID,
    exclude_vulval_site_from_pelvic_leaf,
    pelvic_pain_excluded_concept_ids,
)
from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)

_INT = {PELVIC_PAIN_ID: 1, VULVAL_PAIN_ID: 2, OVARIAN_PAIN_ID: 3}


def _concept_leaf(bitmap_id: str, concept_id: str, term: str, seeds: list[str]) -> dict:
    return {
        "kind": "CONCEPT",
        "bitmap_id": bitmap_id,
        "criterion": {
            "primary_concept_id": concept_id,
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "soft_qualifiers": [],
        },
        "seed_concept_ids": seeds,
    }


def _compiled(seeds: list[str]) -> dict:
    return {
        "rule_id": "1.5.2",
        "name": "1.5.2",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": {
            "kind": "AND",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "sex",
                    "operator": "=",
                    "value": "female",
                },
                _concept_leaf("bm_pelvis", PELVIC_PAIN_ID, "Pain in pelvis", seeds),
            ],
        },
    }


def _evaluator(seeds: list[str]) -> GuidelineEvaluator:
    ruleset = {"version": "pelvic-harness", "rules": [_compiled(seeds)]}
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    store.get_int_id.side_effect = lambda cid: _INT.get(cid)
    allowed = {_INT[cid] for cid in seeds if cid in _INT}
    store.get_bitmap.side_effect = lambda bid: BitMap(allowed)
    store.get_int_ids_bulk.side_effect = lambda cids: {
        cid: _INT[cid] for cid in cids if cid in _INT
    }
    store.get_bitmaps_bulk.side_effect = lambda bids: {"bm_pelvis": BitMap(allowed)}
    return GuidelineEvaluator(store=store)


def _fired(result: dict) -> set[str]:
    return {str(r.get("rule_id")) for r in result.get("matched_rules") or []}


def test_excluded_ids_include_vulval_pain_not_ovarian_pain() -> None:
    ids = set(pelvic_pain_excluded_concept_ids())
    assert VULVAL_PAIN_ID in ids
    assert "275321000" in ids
    assert OVARIAN_PAIN_ID not in ids
    assert PELVIC_PAIN_ID not in ids


def test_exclude_helper_writes_ids_on_pelvic_leaf() -> None:
    tree = {
        "kind": "AND",
        "children": [
            {"kind": "DEMOGRAPHIC", "field": "sex", "operator": "=", "value": "female"},
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": PELVIC_PAIN_ID,
                    "preferred_term": "Pain in pelvis (finding)",
                    "primary_concept_id": PELVIC_PAIN_ID,
                    "excluded_concept_ids": [],
                },
            },
        ],
    }
    out = exclude_vulval_site_from_pelvic_leaf(tree)
    leaf = out["children"][1]["criterion"]
    assert VULVAL_PAIN_ID in leaf["excluded_concept_ids"]
    assert tree["children"][1]["criterion"]["excluded_concept_ids"] == []


def test_1_5_2_does_not_fire_on_vulval_pain_alone() -> None:
    seeds = [PELVIC_PAIN_ID, OVARIAN_PAIN_ID]
    result = _evaluator(seeds).evaluate_patient(
        [VULVAL_PAIN_ID],
        patient_age=58,
        patient_sex="female",
    )
    assert _fired(result) == set()


def test_1_5_2_still_fires_on_true_pelvic_pain() -> None:
    seeds = [PELVIC_PAIN_ID, OVARIAN_PAIN_ID]
    result = _evaluator(seeds).evaluate_patient(
        [PELVIC_PAIN_ID],
        patient_age=58,
        patient_sex="female",
    )
    assert _fired(result) == {"1.5.2"}
