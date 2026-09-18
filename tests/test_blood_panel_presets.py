"""Verification tests for the standard NHS blood panel presets.

Atlas trace:
  DI: DI-5C9CA57B (form checkbox normalisation)
  DI: DI-26546721 (referral form teaching)

The NHS blood results table on a 2WW referral is the same across
trusts. These tests pin the canonical preset so a form teacher does
not have to hand-type every battery, analyte, and SNOMED code.
"""

from __future__ import annotations

import re

from libs.pipeline.blood_panel_presets import (
    NHS_BLOOD_PANEL_BATTERIES,
    blood_panel_preset_payload,
    preset_analytes_for_label,
    unverified_preset_codes,
)

_SCTID_RE = re.compile(r"^\d{6,18}$")

EXPECTED_BATTERY_LABELS = [
    "FBC",
    "UE",
    "LFT",
    "CRP",
    "ESR",
    "TFTs",
    "INR",
    "Bone",
    "Iron",
    "Vitamins",
    "Lipids",
    "Random Glucose",
    "Fasting Glucose",
    "Fasting Chol.",
    "HbA1c",
    "CA 125",
    "FIT",
]


def test_battery_labels_match_the_sherwood_blood_table() -> None:
    labels = [b.label for b in NHS_BLOOD_PANEL_BATTERIES]
    assert labels == EXPECTED_BATTERY_LABELS


def test_fbc_carries_the_five_standard_analytes() -> None:
    fbc = next(b for b in NHS_BLOOD_PANEL_BATTERIES if b.label == "FBC")
    assert fbc.procedure_snomed == "26604007"
    assert fbc.procedure_display == "Complete blood count"
    assert [a.label for a in fbc.analytes] == ["Hb", "WCC", "Plts", "MCV", "Neut"]


def test_every_populated_code_looks_like_a_snomed_identifier() -> None:
    for battery in NHS_BLOOD_PANEL_BATTERIES:
        if battery.procedure_snomed:
            assert _SCTID_RE.match(battery.procedure_snomed), battery.label
        for analyte in battery.analytes:
            if analyte.snomed_code:
                assert _SCTID_RE.match(analyte.snomed_code), analyte.label


def test_every_row_has_a_label_and_a_display_name() -> None:
    for battery in NHS_BLOOD_PANEL_BATTERIES:
        assert battery.label.strip()
        assert battery.procedure_display.strip()
        for analyte in battery.analytes:
            assert analyte.label.strip()
            assert analyte.display.strip()


def test_payload_is_json_safe_and_matches_form_schema_item_shape() -> None:
    payload = blood_panel_preset_payload()
    assert isinstance(payload, list)
    assert len(payload) == len(EXPECTED_BATTERY_LABELS)
    first = payload[0]
    assert set(first) == {
        "pattern",
        "entity_text",
        "semantic_tag",
        "assertion",
        "procedure_snomed",
        "procedure_display",
        "analytes",
        "value_placeholder",
    }
    assert first["pattern"] == "FBC"
    assert first["semantic_tag"] == "procedure"
    assert first["assertion"] == "present"
    assert set(first["analytes"][0]) == {"label", "snomed_code", "display"}


def test_preset_analytes_lookup_is_case_and_space_insensitive() -> None:
    assert [a["label"] for a in preset_analytes_for_label(" fbc ")] == [
        "Hb",
        "WCC",
        "Plts",
        "MCV",
        "Neut",
    ]
    assert preset_analytes_for_label("u&e")[0]["label"] == "Na"
    assert preset_analytes_for_label("not a battery") == []


def test_unverified_codes_are_declared_not_invented() -> None:
    unverified = unverified_preset_codes()
    assert "Bone / Ca cor" in unverified
    assert "Iron" in unverified
    for reason in unverified.values():
        assert reason.strip()


def test_a_quantitative_fit_row_is_a_known_battery() -> None:
    """The FIT row on a 2WW referral must code deterministically.

    NHS 4568668417 had "08/06/2026 Quantitative faecal immunochemical
    test | < 4 ug/g" in the same markdown table as Bone profile and
    U&E, and it was never coded. The phrase already has an approved
    SurfaceForm, so the miss was recall: the model simply never emitted
    the span. A preset battery takes the model out of the loop, the way
    it already does for FBC and CA 125.
    """
    from libs.pipeline.blood_panel_presets import battery_for_label

    for label in (
        "FIT",
        "QFIT",
        "Quantitative faecal immunochemical test",
        "faecal immunochemical test",
    ):
        battery = battery_for_label(label)
        assert battery is not None, f"{label!r} is not a known battery"
        assert battery.procedure_snomed == "149421000000109"
        assert [a.snomed_code for a in battery.analytes] == ["1049361000000101"]


def test_the_fit_preset_codes_are_in_the_fit_investigation_family() -> None:
    """A coded FIT must satisfy the guideline that asks for a FIT.

    Without this the row codes cleanly and NG12 1.3.1 still asks for a
    test the record already holds.
    """
    from libs.guidelines.investigation_family_catalog import FIT_MEMBER_IDS
    from libs.pipeline.blood_panel_presets import battery_for_label

    battery = battery_for_label("FIT")
    assert battery is not None
    assert battery.procedure_snomed in FIT_MEMBER_IDS
    for analyte in battery.analytes:
        assert analyte.snomed_code in FIT_MEMBER_IDS
