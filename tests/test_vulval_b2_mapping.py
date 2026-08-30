"""Ticked B2 must seed a lookup-able vulval mass phrase.

NICE 1.5.17 is lump or ulcer or bleeding. A Sherwood B2 tick means a
lesion on the vulva. Lookup uses the taught entity text, not the B2
token. Free-text synonyms live on Neo4j SurfaceForm, not the old
mapping JSON.

Atlas: DO-62FE139E, VT-766B13F8.
"""

from __future__ import annotations

import json
from pathlib import Path

_FORM = Path(__file__).resolve().parents[1] / (
    "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
)


def test_b2_entity_text_is_a_vulval_mass_phrase() -> None:
    schema = json.loads(_FORM.read_text())
    items = [
        item
        for section in schema.get("sections") or []
        for item in section.get("items") or []
        if str(item.get("pattern") or "").startswith("B2")
    ]
    assert items, "SFH gynae form must teach B2"
    text = str(items[0].get("entity_text") or "").lower()
    assert "vulval lump" in text or "mass of vulva" in text or "vulval mass" in text
