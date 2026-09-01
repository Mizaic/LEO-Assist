"""NG12 1.5.12 / 1.5.14 match PMB or the split-code pair.

Dry-run misses used postmenopausal state (76498008) plus vaginal
bleeding (289530006) instead of 76742009. The rule must fire on
either the single code or that pair. Any bleeding alone must not.

Atlas: UN-5F3BF083, DI-8BAC9BB3, DO-ABE2AE61, VT-E053BB7C.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pyroaring import BitMap

from libs.guidelines.pmb_endometrial import (
    HEAVY_PV_BLEED_ID,
    MENOPAUSE_PRESENT_ID,
    PMB_CONCEPT_ID,
    POSTMENOPAUSAL_STATE_ID,
    PV_BLEEDING_ID,
    build_pmb_1_5_12_logic,
    build_pmb_1_5_14_logic,
)
from services.api.app.services.guidance_rule_edit import validate_logic_tree
from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)

_PMB = PMB_CONCEPT_ID
_STATE = POSTMENOPAUSAL_STATE_ID
_MENO = MENOPAUSE_PRESENT_ID
_BLEED = PV_BLEEDING_ID
_HEAVY = HEAVY_PV_BLEED_ID
_INT = {_PMB: 1, _STATE: 2, _BLEED: 3, _HEAVY: 4, _MENO: 5}


def _concept_leaf(bitmap_id: str, concept_id: str, term: str) -> dict:
    return {
        "kind": "CONCEPT",
        "bitmap_id": bitmap_id,
        "criterion": {
            "primary_concept_id": concept_id,
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "soft_qualifiers": [{"kind": "unexplained", "enforcement": "soft"}],
        },
        "seed_concept_ids": [concept_id],
    }


def _compiled_pmb_rule(rule_id: str, age_op: str, age_value: float) -> dict:
    return {
        "rule_id": rule_id,
        "name": rule_id,
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
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": age_op,
                    "value": age_value,
                    "unit": "years",
                },
                {
                    "kind": "OR",
                    "children": [
                        _concept_leaf("bm_pmb", _PMB, "Postmenopausal bleeding"),
                        {
                            "kind": "AND",
                            "children": [
                                {
                                    "kind": "OR",
                                    "children": [
                                        _concept_leaf(
                                            "bm_state",
                                            _STATE,
                                            "Postmenopausal state",
                                        ),
                                        _concept_leaf(
                                            "bm_meno",
                                            _MENO,
                                            "Menopause present",
                                        ),
                                    ],
                                },
                                {
                                    "kind": "OR",
                                    "children": [
                                        _concept_leaf(
                                            "bm_bleed",
                                            _BLEED,
                                            "Bleeding from vagina",
                                        ),
                                        _concept_leaf(
                                            "bm_heavy",
                                            _HEAVY,
                                            "Heavy vaginal bleeding",
                                        ),
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    }


def _evaluator() -> GuidelineEvaluator:
    ruleset = {
        "version": "pmb-harness",
        "rules": [
            _compiled_pmb_rule("1.5.12", ">=", 55.0),
            _compiled_pmb_rule("1.5.14", "<", 55.0),
        ],
    }
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    store.get_int_id.side_effect = lambda cid: _INT.get(cid)
    bitmaps = {
        "bm_pmb": BitMap([1]),
        "bm_state": BitMap([2]),
        "bm_bleed": BitMap([3]),
        "bm_heavy": BitMap([4]),
        "bm_meno": BitMap([5]),
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


def _concept_ids(node) -> set[str]:
    found: set[str] = set()
    crit = getattr(node, "criterion", None)
    if crit is not None and crit.snomed_concept_id:
        found.add(crit.snomed_concept_id)
    for child in node.children or []:
        found |= _concept_ids(child)
    return found


def _or_arm(node):
    for child in node.children or []:
        if child.kind == "OR":
            return child
    raise AssertionError("expected an OR arm under the root AND")


def test_1_5_12_tree_is_single_code_or_split_pair() -> None:
    tree = build_pmb_1_5_12_logic()
    assert tree.kind == "AND"
    ids = validate_logic_tree(tree)
    assert {_PMB, _STATE, _MENO, _BLEED, _HEAVY} <= set(ids)
    or_arm = _or_arm(tree)
    assert len(or_arm.children or []) == 2
    singles = [c for c in or_arm.children or [] if c.kind == "CONCEPT"]
    pairs = [c for c in or_arm.children or [] if c.kind == "AND"]
    assert [c.criterion.snomed_concept_id for c in singles] == [_PMB]
    assert _concept_ids(pairs[0]) == {_STATE, _MENO, _BLEED, _HEAVY}


def test_1_5_14_tree_keeps_under_55_and_female() -> None:
    tree = build_pmb_1_5_14_logic()
    assert tree.kind == "AND"
    fields = {
        (c.field, c.operator, str(c.value))
        for c in (tree.children or [])
        if c.kind == "DEMOGRAPHIC"
    }
    assert ("sex", "=", "female") in fields
    assert ("age", "<", "55") in fields


def test_unexplained_is_soft_on_pmb_and_pair_arms() -> None:
    for tree in (build_pmb_1_5_12_logic(), build_pmb_1_5_14_logic()):
        quals = []
        for node in _walk(tree):
            if node.kind != "CONCEPT" or node.criterion is None:
                continue
            quals.extend(node.criterion.soft_qualifiers)
        assert quals, "PMB / pair arm must carry unexplained"
        assert all(q.kind == "unexplained" for q in quals)
        assert all(q.enforcement == "soft" for q in quals)


def _walk(node):
    yield node
    for child in node.children or []:
        yield from _walk(child)


def test_1_5_12_fires_on_split_codes_age_59_without_76742009() -> None:
    result = _evaluator().evaluate_patient(
        [_STATE, _BLEED],
        patient_age=59,
        patient_sex="female",
        letter_text="PMB for 10 days",
    )
    assert _fired(result) == {"1.5.12"}


def test_1_5_14_fires_on_split_codes_under_55() -> None:
    result = _evaluator().evaluate_patient(
        [_STATE, _BLEED],
        patient_age=49,
        patient_sex="female",
        letter_text="3 years no periods then heavy bleeding",
    )
    assert _fired(result) == {"1.5.14"}


def test_single_pmb_code_still_fires_both_age_bands() -> None:
    older = _evaluator().evaluate_patient(
        [_PMB],
        patient_age=59,
        patient_sex="female",
    )
    younger = _evaluator().evaluate_patient(
        [_PMB],
        patient_age=53,
        patient_sex="female",
    )
    assert _fired(older) == {"1.5.12"}
    assert _fired(younger) == {"1.5.14"}


def test_1_5_14_fires_on_menopause_present_plus_heavy_pv_bleed() -> None:
    result = _evaluator().evaluate_patient(
        [_MENO, _HEAVY],
        patient_age=49,
        patient_sex="female",
        letter_text="menopause then heavy vaginal bleeding",
    )
    assert _fired(result) == {"1.5.14"}


def test_1_5_14_fires_on_state_plus_heavy_pv_bleed() -> None:
    result = _evaluator().evaluate_patient(
        [_STATE, _HEAVY],
        patient_age=49,
        patient_sex="female",
        letter_text="menopause then heavy vaginal bleeding",
    )
    assert _fired(result) == {"1.5.14"}


def test_heavy_vaginal_bleeding_alone_does_not_fire() -> None:
    result = _evaluator().evaluate_patient(
        [_HEAVY],
        patient_age=49,
        patient_sex="female",
        letter_text="heavy vaginal bleeding",
    )
    assert _fired(result) == set()


def test_vaginal_bleeding_alone_does_not_fire() -> None:
    result = _evaluator().evaluate_patient(
        [_BLEED],
        patient_age=59,
        patient_sex="female",
        letter_text="PV bleeding",
    )
    assert _fired(result) == set()


def test_soft_unexplained_does_not_block_when_word_absent() -> None:
    result = _evaluator().evaluate_patient(
        [_PMB],
        patient_age=59,
        patient_sex="female",
        letter_text="postmenopausal bleeding",
    )
    assert "1.5.12" in _fired(result)
    unmatched = result["matched_rules"][0].get("unverified_qualifiers") or []
    assert "unexplained" in unmatched
