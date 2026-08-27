"""Structural validation tests for the SFH Gynaecology 2WW template fixture.

Validates that the fixture loaded from disk has the correct section count,
expected section IDs, a populated blood panel, and completeness rules
covering the symptom criteria and cancer type sections.

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures/form_schema/sfh_gynae_2ww_template.json"
)

EXPECTED_SECTION_IDS = {
    "section_a_cancer_type",
    "section_b_symptoms",
    "primary_care_pathway",
    "patient_awareness",
    "section_c_clinical_details",
    "section_d_investigations",
    "section_e_performance",
}

BLOOD_BATTERY_LABELS = {
    "FBC",
    "UE",
    "LFT",
    "Bone",
    "CRP",
    "TFTs",
    "Iron",
    "Vitamins",
    "Lipids",
    "Random Glucose",
    "Fasting Glucose",
    "HbA1c",
    "CA 125",
}

CANCER_TYPE_ITEMS = {"Ovary", "Cervix", "Endometrium", "Vagina", "Vulva"}

SYMPTOM_PREFIXES = {"B1.", "B2.", "B3.", "B4.", "B5.", "B6.", "B7.", "B8.", "B9."}


@pytest.fixture(scope="module")
def template() -> dict:
    assert FIXTURE_PATH.exists(), f"Fixture not found: {FIXTURE_PATH}"
    with open(FIXTURE_PATH, encoding="ascii") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def sections_by_id(template: dict) -> dict:
    return {s["section_id"]: s for s in template["sections"]}


def test_fixture_loads(template: dict) -> None:
    assert template["form_name"], "form_name must not be empty"
    assert template["status"] == "active"
    assert template["organization_id"] == "sfh-nhs-trust"
    assert template["service_id"] == "sfh-gynae-2ww"


def test_section_count(template: dict) -> None:
    assert (
        len(template["sections"]) == 7
    ), "Expected 7 sections (A, B, PMB pathway, patient awareness, C, D, E)"


def test_all_section_ids_present(sections_by_id: dict) -> None:
    missing = EXPECTED_SECTION_IDS - set(sections_by_id)
    assert not missing, f"Missing sections: {missing}"


def test_all_sections_have_start_pattern(template: dict) -> None:
    for sec in template["sections"]:
        assert sec.get(
            "start_pattern"
        ), f"Section {sec['section_id']} has no start_pattern"


def test_section_a_cancer_types(sections_by_id: dict) -> None:
    sec = sections_by_id["section_a_cancer_type"]
    assert sec["section_type"] == "checkbox"
    patterns = {i["pattern"] for i in sec["items"]}
    missing = CANCER_TYPE_ITEMS - patterns
    assert not missing, f"Section A missing cancer types: {missing}"
    assert "394586005" in sec.get("semantic_tags", [])


def test_section_b_all_nine_items(sections_by_id: dict) -> None:
    sec = sections_by_id["section_b_symptoms"]
    assert sec["section_type"] == "checkbox"
    patterns = " ".join(i["pattern"] for i in sec["items"])
    for prefix in SYMPTOM_PREFIXES:
        assert prefix in patterns, f"Section B missing item {prefix}"


def test_section_d_ordered_tests_type(sections_by_id: dict) -> None:
    sec = sections_by_id["section_d_investigations"]
    assert sec["section_type"] == "ordered_tests"


def test_blood_panel_batteries_present(sections_by_id: dict) -> None:
    sec = sections_by_id["section_d_investigations"]
    battery_labels = {i["pattern"] for i in sec["items"]}
    missing = BLOOD_BATTERY_LABELS - battery_labels
    assert not missing, f"Blood panel missing batteries: {missing}"


def test_fbc_has_analytes(sections_by_id: dict) -> None:
    sec = sections_by_id["section_d_investigations"]
    fbc = next(i for i in sec["items"] if i["pattern"] == "FBC")
    assert fbc["procedure_snomed"] == "26604007"
    analyte_labels = {a["label"] for a in fbc["analytes"]}
    assert analyte_labels == {"Hb", "WCC", "Plts", "MCV", "Neut"}


def test_ca125_present(sections_by_id: dict) -> None:
    sec = sections_by_id["section_d_investigations"]
    ca = next((i for i in sec["items"] if i["pattern"] == "CA 125"), None)
    assert ca is not None
    assert ca["procedure_snomed"] == "909121000000107"


def test_section_e_frailty_scale_nine_items(sections_by_id: dict) -> None:
    sec = sections_by_id["section_e_performance"]
    assert sec["section_type"] == "checkbox"
    assert len(sec["items"]) == 9, "Clinical Frailty Scale must have 9 items"


def test_completeness_groups_present(template: dict) -> None:
    groups = template.get("completeness_groups", [])
    assert len(groups) >= 2, "Expected at least 2 completeness groups"


def test_completeness_cancer_type_required(template: dict) -> None:
    groups = {g["name"]: g for g in template["completeness_groups"]}
    assert "cancer_type_required" in groups
    grp = groups["cancer_type_required"]
    assert grp["required"] is True
    assert grp["min_count"] >= 1


def test_completeness_symptom_criterion(template: dict) -> None:
    groups = {g["name"]: g for g in template["completeness_groups"]}
    assert "symptom_criterion_required" in groups
    grp = groups["symptom_criterion_required"]
    assert grp["required"] is True
    assert len(grp["members"]) == 9, "All 9 symptom criteria must be in the group"


def test_no_pii_in_fixture(template: dict) -> None:
    raw = json.dumps(template)
    for token in ("[NAME]", "[NHS_NUMBER]", "[DOB]", "[PHONE]", "[ADDRESS]", "[UBRN]"):
        assert token not in raw, f"PII token {token!r} found in fixture"
