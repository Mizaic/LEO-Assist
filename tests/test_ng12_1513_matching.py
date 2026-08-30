"""1.5.13 fires on discharge when first-presentation is soft, not contradicted.

first_presentation sits on the first-time OR arm only. Soft not-confirmed
still allows that arm. Contradicted first-presentation needs platelets
or haematuria. Evaluate uses the published tree shape, not a reshape
at match time.

Atlas: DI-8BAC9BB3, DI-C136E4B7, VT-9CEA9081.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)

_DISCHARGE = "271939006"
_THROMBO = "6631009"
_HAEM = "34436003"
_INT = {_DISCHARGE: 1, _THROMBO: 2, _HAEM: 3}


def _concept(
    bitmap_id: str, concept_id: str, term: str, quals: list | None = None
) -> dict:
    return {
        "kind": "CONCEPT",
        "bitmap_id": bitmap_id,
        "criterion": {
            "primary_concept_id": concept_id,
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "soft_qualifiers": quals or [],
        },
        "seed_concept_ids": [concept_id],
    }


def _compiled_1513() -> dict:
    first_q = {
        "kind": "first_presentation",
        "enforcement": "soft",
        "concept_id": _DISCHARGE,
        "within_days": 90,
    }
    return {
        "rule_id": "1.5.13",
        "name": "1.5.13 Gynaecological cancers",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": {
            "kind": "AND",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": ">=",
                    "value": 55.0,
                    "unit": "years",
                },
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "sex",
                    "operator": "=",
                    "value": "female",
                },
                {
                    "kind": "AND",
                    "children": [
                        _concept(
                            "bm_disch",
                            _DISCHARGE,
                            "Vaginal discharge",
                            [{"kind": "unexplained", "enforcement": "soft"}],
                        ),
                        {
                            "kind": "OR",
                            "children": [
                                _concept(
                                    "bm_disch",
                                    _DISCHARGE,
                                    "Vaginal discharge",
                                    [first_q],
                                ),
                                _concept("bm_thrombo", _THROMBO, "Thrombocytosis"),
                                _concept("bm_haem", _HAEM, "Blood in urine"),
                            ],
                        },
                    ],
                },
            ],
        },
    }


def _evaluator() -> GuidelineEvaluator:
    ruleset = {"version": "1513-harness", "rules": [_compiled_1513()]}
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    store.get_int_id.side_effect = lambda cid: _INT.get(cid)
    bitmaps = {
        "bm_disch": BitMap([1]),
        "bm_thrombo": BitMap([2]),
        "bm_haem": BitMap([3]),
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


def test_discharge_age_55_female_fires_when_first_presentation_not_confirmed() -> None:
    result = _evaluator().evaluate_patient(
        [_DISCHARGE],
        patient_age=57,
        patient_sex="female",
        letter_text="yellow vaginal discharge",
    )
    assert _fired(result) == {"1.5.13"}


def test_contradicted_first_presentation_without_other_arm_does_not_fire() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=200)
    result = _evaluator().evaluate_patient(
        [_DISCHARGE],
        patient_age=57,
        patient_sex="female",
        letter_text="recurrent vaginal discharge",
        concept_occurrences={_DISCHARGE: [old]},
    )
    assert _fired(result) == set()


def test_contradicted_first_presentation_still_fires_with_thrombocytosis() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=200)
    result = _evaluator().evaluate_patient(
        [_DISCHARGE, _THROMBO],
        patient_age=57,
        patient_sex="female",
        letter_text="recurrent vaginal discharge",
        concept_occurrences={_DISCHARGE: [old]},
    )
    assert _fired(result) == {"1.5.13"}
