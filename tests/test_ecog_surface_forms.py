"""ECOG printed ticks map to one grade each.

Atlas: DI-47D2CD86, DO-5A88E0B9.
"""

from __future__ import annotations

import json
from pathlib import Path

ECOG_0 = "425389002"
ECOG_1 = "422512005"
ECOG_2 = "422894000"
ECOG_3 = "423053003"
ECOG_4 = "423237006"
ECOG_5 = "423409001"

# One phrase, one code. Printed labels and taught entity_text.
ECOG_PHRASES: dict[str, str] = {
    "Fully active": ECOG_0,
    "ECOG 0 fully active": ECOG_0,
    "ECOG 0 fully active without restriction": ECOG_0,
    (
        "0 - Fully active, able to carry on all pre-disease "
        "and performance without restriction"
    ): ECOG_0,
    "Restricted in physically strenuous": ECOG_1,
    "ECOG 1 restricted in strenuous activity": ECOG_1,
    (
        "1 - Restricted in physically strenuous activity but ambulatory "
        "and able to carry out work of a light or sedentary nature "
        "e.g. light house work, office work"
    ): ECOG_1,
    "Ambulatory and capable of all selfcare": ECOG_2,
    "ECOG 2 ambulatory but unable to work": ECOG_2,
    "ECOG 2 ambulatory and capable of selfcare": ECOG_2,
    "confined to bed or chair more than 50%": ECOG_3,
    "ECOG 3 limited selfcare": ECOG_3,
    "Totally confined to bed or chair": ECOG_4,
    "ECOG 4 completely disabled": ECOG_4,
    "ECOG 5 dead": ECOG_5,
}

_BREAST = Path(__file__).parent / "fixtures/form_schema/sfh_breast_2ww_template.json"
_GYNAE = Path(__file__).parent / "fixtures/form_schema/sfh_gynae_2ww_template.json"


def _ecog_items(path: Path) -> list[dict]:
    schema = json.loads(path.read_text(encoding="ascii"))
    return [
        item
        for section in schema.get("sections") or []
        for item in section.get("items") or []
        if str(item.get("entity_text") or "").lower().startswith("ecog ")
    ]


def test_each_phrase_has_one_code() -> None:
    codes = set(ECOG_PHRASES.values())
    assert codes == {ECOG_0, ECOG_1, ECOG_2, ECOG_3, ECOG_4, ECOG_5}


def test_breast_and_gynae_ecog_phrases_are_in_the_table() -> None:
    for path in (_BREAST, _GYNAE):
        for item in _ecog_items(path):
            taught = item["entity_text"]
            if taught.startswith("ECOG 0"):
                continue
            assert taught in ECOG_PHRASES, taught
            printed = item["pattern"]
            if printed.endswith(" ["):
                continue
            assert printed in ECOG_PHRASES, printed


def test_grade_five_is_not_a_form_tick() -> None:
    for path in (_BREAST, _GYNAE):
        texts = {item["entity_text"] for item in _ecog_items(path)}
        assert "ECOG 5 dead" not in texts
