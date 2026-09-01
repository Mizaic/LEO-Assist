"""Breast 2WW taught ticks map to one lump or pain code each.

Atlas: DI-47D2CD86, DO-5A88E0B9.
"""

from __future__ import annotations

import json
from pathlib import Path

BREAST_LUMP = "89164003"
MASTALGIA = "315250005"

# One phrase, one code.
BREAST_TICK_PHRASES: dict[str, str] = {
    "Newly presenting discrete hard breast lump": BREAST_LUMP,
    "Newly presenting discrete hard lump": BREAST_LUMP,
    "Discrete breast lump persisting after period or menopause": BREAST_LUMP,
    "discrete lump that persists post period": BREAST_LUMP,
    "Intractable breast pain": MASTALGIA,
}

_BREAST = Path(__file__).parent / "fixtures/form_schema/sfh_breast_2ww_template.json"


def test_a1_and_a2_entity_texts_map_to_breast_lump() -> None:
    schema = json.loads(_BREAST.read_text(encoding="ascii"))
    taught = {
        item["entity_text"]
        for section in schema.get("sections") or []
        for item in section.get("items") or []
        if item.get("pattern") in {"A1.", "A2.", "A.2"}
    }
    assert taught <= set(BREAST_TICK_PHRASES)
    assert all(BREAST_TICK_PHRASES[text] == BREAST_LUMP for text in taught)


def test_intractable_pain_maps_to_mastalgia() -> None:
    assert BREAST_TICK_PHRASES["Intractable breast pain"] == MASTALGIA
