"""Gynae 2WW taught ticks map to pelvic mass, not 'on examination - suspicious'.

B4 seeds 'Suspicious pelvic mass on ultrasound'. That phrase must resolve
to 74285003 so NG12 1.5.1 can see the tick. 163614007 is the wrong code.

Atlas: DI-47D2CD86, DO-5A88E0B9.
"""

from __future__ import annotations

import json
from pathlib import Path

PELVIC_MASS = "74285003"
OE_SUSPICIOUS = "163614007"

# One phrase, one code. Printed labels and taught entity_text.
GYNAE_MASS_PHRASES: dict[str, str] = {
    "Suspicious pelvic mass on ultrasound": PELVIC_MASS,
    "Suspicious pelvic mass on pelvic ultrasound": PELVIC_MASS,
    "Palpable pelvic mass (not fibroids)": PELVIC_MASS,
    "pelvic mass": PELVIC_MASS,
}

_GYNAE = Path(__file__).parent / "fixtures/form_schema/sfh_gynae_2ww_template.json"


def test_b3_and_b4_entity_texts_map_to_pelvic_mass() -> None:
    schema = json.loads(_GYNAE.read_text(encoding="ascii"))
    taught = {
        item["entity_text"]
        for section in schema.get("sections") or []
        for item in section.get("items") or []
        if item.get("pattern") in {"B3.", "B4."}
    }
    assert taught <= set(GYNAE_MASS_PHRASES)
    assert all(GYNAE_MASS_PHRASES[text] == PELVIC_MASS for text in taught)


def test_pelvic_mass_phrases_are_not_on_examination_suspicious() -> None:
    for phrase, concept_id in GYNAE_MASS_PHRASES.items():
        assert concept_id != OE_SUSPICIOUS
        assert "on examination" not in phrase.lower()
