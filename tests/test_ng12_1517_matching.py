"""NG12 1.5.17 matches lump or swelling or ulcer or bleed.

NICE is any of those unexplained signs. Swelling of vulva is the
lump-like finding coded on Sherwood letters that only say swelling.

Atlas: DI-8BAC9BB3, DO-62FE139E, VT-766B13F8.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pyroaring import BitMap

from libs.guidelines.ng12_1517_vulval import (
    GENITAL_BLEED_ID,
    VULVAL_MASS_ID,
    VULVAL_SWELLING_ID,
    VULVAL_ULCER_ID,
    build_vulval_1_5_17_logic,
)
from services.api.app.services.guidance_rule_edit import validate_logic_tree
from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)

_MASS = VULVAL_MASS_ID
_SWELL = VULVAL_SWELLING_ID
_ULCER = VULVAL_ULCER_ID
_BLEED = GENITAL_BLEED_ID
_INT = {_MASS: 1, _SWELL: 2, _ULCER: 3, _BLEED: 4}


def _concept_leaf(bitmap_id: str, concept_id: str, term: str) -> dict:
    return {
        "kind": "CONCEPT",
        "bitmap_id": bitmap_id,
        "criterion": {
            "primary_concept_id": concept_id,
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "soft_qualifiers": [],
        },
        "seed_concept_ids": [concept_id],
    }


def _compiled() -> dict:
    return {
        "rule_id": "1.5.17",
        "name": "1.5.17",
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
                {
                    "kind": "OR",
                    "children": [
                        _concept_leaf("bm_mass", _MASS, "Mass of vulva"),
                        _concept_leaf("bm_swell", _SWELL, "Swelling of vulva"),
                        _concept_leaf("bm_ulcer", _ULCER, "Ulceration of vulva"),
                        _concept_leaf(
                            "bm_bleed", _BLEED, "Bleeding from genital region"
                        ),
                    ],
                },
            ],
        },
    }


def _evaluator() -> GuidelineEvaluator:
    ruleset = {"version": "vulval-harness", "rules": [_compiled()]}
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    store.get_int_id.side_effect = lambda cid: _INT.get(cid)
    bitmaps = {
        "bm_mass": BitMap([1]),
        "bm_swell": BitMap([2]),
        "bm_ulcer": BitMap([3]),
        "bm_bleed": BitMap([4]),
    }
    store.get_bitmap.side_effect = lambda bid: bitmaps.get(bid)
    store.get_int_ids_bulk.side_effect = lambda cids: {
        cid: _INT[cid] for cid in cids if cid in _INT
    }
    store.get_bitmaps_bulk.side_effect = lambda bids: {
        bid: bm for bid, bm in bitmaps.items() if bid in bids
    }
    return GuidelineEvaluator(store=store)


def _fired(result: dict) -> set[str]:
    return {str(r.get("rule_id")) for r in result.get("matched_rules") or []}


def _or_ids(tree) -> set[str]:
    for child in tree.children or []:
        if child.kind != "OR":
            continue
        return {
            c.criterion.snomed_concept_id
            for c in (child.children or [])
            if c.kind == "CONCEPT" and c.criterion is not None
        }
    raise AssertionError("expected an OR arm")


def test_1_5_17_tree_ors_mass_swelling_ulcer_and_bleed() -> None:
    tree = build_vulval_1_5_17_logic()
    assert tree.kind == "AND"
    ids = set(validate_logic_tree(tree))
    assert {_MASS, _SWELL, _ULCER, _BLEED} <= ids
    assert _or_ids(tree) == {_MASS, _SWELL, _ULCER, _BLEED}


def test_1_5_17_fires_on_swelling_of_vulva_alone() -> None:
    result = _evaluator().evaluate_patient(
        [_SWELL],
        patient_age=68,
        patient_sex="female",
        letter_text="significant swelling of the vulva",
    )
    assert _fired(result) == {"1.5.17"}


def test_1_5_17_fires_on_ulceration_alone() -> None:
    result = _evaluator().evaluate_patient(
        [_ULCER],
        patient_age=58,
        patient_sex="female",
        letter_text="two open vulval sores",
    )
    assert _fired(result) == {"1.5.17"}


def test_1_5_17_does_not_fire_without_female() -> None:
    result = _evaluator().evaluate_patient(
        [_SWELL],
        patient_age=68,
        patient_sex="male",
    )
    assert _fired(result) == set()
