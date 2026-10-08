"""Skipped form sections carry their printed tick boxes.

Auto-detect gives admin and template guidance sections a heading but no
items. The recogniser still counts every tick box on the letter, so a
form taught from a letter with transport, interpreter or Hospital Use
Only boxes was refused because it did not match its own letter.

Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1.
Risk R-B88CCFD6.
"""

from __future__ import annotations

import copy
from pathlib import Path

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_checkbox_seed import seed_checkbox_entities
from libs.pipeline.form_schema_normalizer import FormSchema, apply_schema_to_text
from libs.pipeline.form_schema_request import build_sections_from_request
from libs.pipeline.form_skip_boxes import fill_skip_section_boxes
from libs.pipeline.form_teach_guard import teach_problems

LETTER = (
    Path(__file__).parent / "fixtures" / "form_schema" / "sfh_lower_gi_2ww_deid.md"
).read_text(encoding="utf-8")

SYMPTOMS = [
    "Change in bowel habit",
    "New onset of abdominal pain",
    "Definite palpable abdominal mass",
    "Unexplained iron deficiency anaemia",
    "New onset of constipation",
    "New onset of Diarrhoea",
    "Significant unexplained weight loss",
    "Rectal mass",
    "Unexplained rectal bleeding",
]
FRAILTY = [
    "Very Fit",
    "Managing well",
    "Very Mild",
    "Mild",
    "Moderate",
    "Severe",
    "Very severe",
    "Terminally ill",
]
DEMOGRAPHIC_BOXES = [
    "Tick if Transport required",
    "Tick if Interpreter required",
    "Tick if Communication / Capacity issues",
]
HOSPITAL_BOXES = ["Pt Contacted", "Interpreter Booked", "Transport Booked", "Accepted"]


def _section(sid: str, stype: str, label: str, items: list[str] = ()) -> dict:
    return {
        "section_id": sid,
        "section_type": stype,
        "label": label,
        "start_pattern": label,
        "items": [{"pattern": p, "entity_text": p} for p in items],
    }


def _detected() -> list[dict]:
    """The sections auto-detect gives: admin sections are heading only."""
    return [
        _section("S1", "admin", "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS"),
        _section(
            "S2",
            "checkbox_multi",
            "SECTION 2: Symptoms suggesting colorectal cancer",
            SYMPTOMS,
        ),
        _section("S3", "scale", "Performance Status - Clinical Frailty Scale", FRAILTY),
        _section("S4", "free_text", "SECTION 3 - PAST MEDICAL HISTORY"),
        _section("S5", "admin", "Hospital Use Only"),
    ]


def _patterns(sections: list[dict], sid: str) -> list[str]:
    (section,) = [s for s in sections if s["section_id"] == sid]
    return [item["pattern"] for item in section["items"]]


def _schema(sections: list[dict]) -> FormSchema:
    return FormSchema(
        schema_id="",
        fingerprint="sfh-lower-gi-test",
        form_name="Sherwood Lower GI",
        sections=build_sections_from_request(sections),
        created_by="test",
    )


def test_admin_sections_gain_their_printed_tick_boxes() -> None:
    filled = fill_skip_section_boxes(_detected(), LETTER)
    assert _patterns(filled, "S1") == DEMOGRAPHIC_BOXES
    assert _patterns(filled, "S5") == HOSPITAL_BOXES


def test_a_label_stops_before_the_box() -> None:
    filled = fill_skip_section_boxes(_detected(), LETTER)
    labels = _patterns(filled, "S1") + _patterns(filled, "S5")
    assert not any("interpreter details recorded" in label for label in labels)
    assert not any("[" in label or "/N" in label for label in labels)


def test_a_label_after_the_box_is_used_when_nothing_comes_before() -> None:
    text = "| Hospital Use Only |\n| [ ] Patient declined transport |\n"
    filled = fill_skip_section_boxes(
        [_section("H", "admin", "Hospital Use Only")], text
    )
    assert _patterns(filled, "H") == ["Patient declined transport"]


def test_running_the_fill_twice_adds_nothing_new() -> None:
    once = fill_skip_section_boxes(_detected(), LETTER)
    assert fill_skip_section_boxes(copy.deepcopy(once), LETTER) == once


def test_a_label_the_section_already_has_is_not_added_again() -> None:
    sections = _detected()
    sections[4]["items"] = [{"pattern": "Pt Contacted", "entity_text": "Pt Contacted"}]
    filled = fill_skip_section_boxes(sections, LETTER)
    assert _patterns(filled, "S5") == HOSPITAL_BOXES


def test_other_section_types_are_never_changed() -> None:
    before = _detected()
    filled = fill_skip_section_boxes(copy.deepcopy(before), LETTER)
    for index in (1, 2, 3):
        assert filled[index] == before[index]


def test_template_guidance_sections_are_filled_too() -> None:
    text = "| Points to remember |\n| Bloating noted [ ] |\n"
    sections = [_section("N", "template_noise", "Points to remember")]
    assert _patterns(fill_skip_section_boxes(sections, text), "N") == ["Bloating noted"]


def test_boxes_before_the_first_heading_are_ignored() -> None:
    text = "| Tick if urgent [ ] |\n| Hospital Use Only |\n| Accepted Y [ ] |\n"
    filled = fill_skip_section_boxes(
        [_section("H", "admin", "Hospital Use Only")], text
    )
    assert _patterns(filled, "H") == ["Accepted"]


def test_the_input_sections_are_not_changed_in_place() -> None:
    sections = _detected()
    fill_skip_section_boxes(sections, LETTER)
    assert sections == _detected()


def test_a_heading_only_form_now_recognises_its_own_letter() -> None:
    detected = _detected()
    assert teach_problems(_schema(detected), LETTER, [])
    filled = fill_skip_section_boxes(detected, LETTER)
    assert teach_problems(_schema(filled), LETTER, []) == []


def test_admin_lines_stay_masked_and_never_become_facts() -> None:
    schema = _schema(fill_skip_section_boxes(_detected(), LETTER))
    rewritten = apply_schema_to_text(LETTER, schema).splitlines()
    for label in DEMOGRAPHIC_BOXES[:1] + HOSPITAL_BOXES:
        (line,) = [ln for ln in rewritten if label in ln]
        assert line.startswith(NON_EXTRACTABLE_MARKER), line
    seeded = {str(e.get("text") or "") for e in seed_checkbox_entities(LETTER, schema)}
    assert not seeded.intersection(DEMOGRAPHIC_BOXES + HOSPITAL_BOXES)
