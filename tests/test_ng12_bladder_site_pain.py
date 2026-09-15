"""NG12 must not treat bladder-site pain as abdominal or pelvic pain.

NHS 4243356475: Pain of urinary bladder 15803009 is a SNOMED child of
Abdominal pain 21522001 and Pain in pelvis 30473006. That fired
1.3.1 (FIT) and 1.5.2 (ovarian tests) with no abdominal pain in the notes.

Owner: AppropriatenessRule.logicJson excluded_concept_ids on those leaves.

Atlas: UN-5F3BF083.
"""

from __future__ import annotations

from libs.guidelines.bladder_site_pain import (
    ABDOMINAL_PAIN_ID,
    BLADDER_PAIN_ID,
    GALLBLADDER_PAIN_ID,
    PELVIC_PAIN_ID,
    bladder_site_excluded_concept_ids,
    exclude_bladder_site_from_pain_leaves,
)


def test_excluded_ids_are_urinary_bladder_not_gallbladder() -> None:
    ids = set(bladder_site_excluded_concept_ids())
    assert BLADDER_PAIN_ID in ids
    assert "16580691000119107" in ids
    assert "38731000087104" in ids
    assert "6744007" in ids
    assert "16844001" in ids
    assert GALLBLADDER_PAIN_ID not in ids
    assert ABDOMINAL_PAIN_ID not in ids
    assert PELVIC_PAIN_ID not in ids


def test_helper_writes_ids_on_abdominal_and_pelvic_leaves_only() -> None:
    tree = {
        "kind": "OR",
        "children": [
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": ABDOMINAL_PAIN_ID,
                    "preferred_term": "Abdominal pain (finding)",
                    "excluded_concept_ids": [],
                },
            },
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": PELVIC_PAIN_ID,
                    "preferred_term": "Pain in pelvis (finding)",
                    "excluded_concept_ids": ["162145001"],
                },
            },
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": "75088002",
                    "preferred_term": "Urgent desire to urinate (finding)",
                    "excluded_concept_ids": [],
                },
            },
        ],
    }
    out = exclude_bladder_site_from_pain_leaves(tree)
    abdo = out["children"][0]["criterion"]["excluded_concept_ids"]
    pelvic = out["children"][1]["criterion"]["excluded_concept_ids"]
    urgency = out["children"][2]["criterion"]["excluded_concept_ids"]
    assert BLADDER_PAIN_ID in abdo
    assert BLADDER_PAIN_ID in pelvic
    assert "162145001" in pelvic
    assert urgency == []
    assert tree["children"][0]["criterion"]["excluded_concept_ids"] == []


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


def _evaluator(rule_id: str, extra: dict, seeds: list[str]):
    from unittest.mock import MagicMock

    from pyroaring import BitMap

    from services.terminology_api.app.services.bitmap_store import BitmapStore
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    int_map = {
        ABDOMINAL_PAIN_ID: 1,
        PELVIC_PAIN_ID: 2,
        BLADDER_PAIN_ID: 3,
    }
    allowed = {int_map[cid] for cid in seeds if cid in int_map}
    ruleset = {
        "version": "bladder-harness",
        "rules": [
            {
                "rule_id": rule_id,
                "name": rule_id,
                "schema_version": 2,
                "guideline_id": "NG12",
                "logic_tree": extra,
            }
        ],
    }
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    store.get_int_id.side_effect = lambda cid: int_map.get(cid)
    store.get_bitmap.side_effect = lambda bid: BitMap(allowed)
    store.get_int_ids_bulk.side_effect = lambda cids: {
        cid: int_map[cid] for cid in cids if cid in int_map
    }
    store.get_bitmaps_bulk.side_effect = lambda bids: {
        "bm_pain": BitMap(allowed),
    }
    return GuidelineEvaluator(store=store)


def _fired(result: dict) -> set[str]:
    return {str(r.get("rule_id")) for r in result.get("matched_rules") or []}


def test_1_3_1_does_not_fire_on_bladder_pain_alone() -> None:
    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "DEMOGRAPHIC",
                "field": "age",
                "operator": ">=",
                "value": 50.0,
                "unit": "years",
            },
            _concept_leaf(
                "bm_pain",
                ABDOMINAL_PAIN_ID,
                "Abdominal pain",
                [ABDOMINAL_PAIN_ID],
            ),
        ],
    }
    result = _evaluator("1.3.1", tree, [ABDOMINAL_PAIN_ID]).evaluate_patient(
        [BLADDER_PAIN_ID],
        patient_age=55,
        patient_sex="female",
    )
    assert _fired(result) == set()


def test_1_5_2_does_not_fire_on_bladder_pain_alone() -> None:
    tree = {
        "kind": "AND",
        "children": [
            {"kind": "DEMOGRAPHIC", "field": "sex", "operator": "=", "value": "female"},
            {
                "kind": "OR",
                "children": [
                    _concept_leaf(
                        "bm_pain",
                        PELVIC_PAIN_ID,
                        "Pain in pelvis",
                        [PELVIC_PAIN_ID],
                    ),
                    _concept_leaf(
                        "bm_pain",
                        ABDOMINAL_PAIN_ID,
                        "Abdominal pain",
                        [ABDOMINAL_PAIN_ID],
                    ),
                ],
            },
        ],
    }
    result = _evaluator("1.5.2", tree, [PELVIC_PAIN_ID, ABDOMINAL_PAIN_ID]).evaluate_patient(
        [BLADDER_PAIN_ID],
        patient_age=55,
        patient_sex="female",
    )
    assert _fired(result) == set()


def test_1_5_2_still_fires_on_true_pelvic_pain() -> None:
    tree = {
        "kind": "AND",
        "children": [
            {"kind": "DEMOGRAPHIC", "field": "sex", "operator": "=", "value": "female"},
            _concept_leaf(
                "bm_pain",
                PELVIC_PAIN_ID,
                "Pain in pelvis",
                [PELVIC_PAIN_ID],
            ),
        ],
    }
    result = _evaluator("1.5.2", tree, [PELVIC_PAIN_ID]).evaluate_patient(
        [PELVIC_PAIN_ID],
        patient_age=55,
        patient_sex="female",
    )
    assert _fired(result) == {"1.5.2"}
