"""Structural validation tests for the SFH Gynaecology 2WW template fixture.

Validates that the fixture loaded from disk has the correct section count,
expected section IDs, a populated blood panel, and completeness rules
covering the symptom criteria and cancer type sections.

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

import json
import sys
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
    "ecog_status",
    "points_to_remember",
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
    assert template["organization_id"] == "RK5"
    assert template["service_id"] == "7980224"


def test_runtime_seed_and_resolver_have_no_live_node_id_literals() -> None:
    """RK5 / 7980224 are fixture example data, not production constants."""
    repo = Path(__file__).parent.parent
    runtime_files = (
        repo / "scripts/seed_sfh_gynae_2ww_template.py",
        repo / "libs/pipeline/form_schema_store.py",
        repo / "services/api/app/routers/form_schema.py",
        repo / "libs/pipeline_graph/subgraphs/extraction.py",
    )
    for path in runtime_files:
        src = path.read_text(encoding="utf-8")
        assert "RK5" not in src, f"{path.name} must not hardcode Organization.id"
        assert "7980224" not in src, f"{path.name} must not hardcode Service.id"


def test_build_payload_reads_scope_from_fixture(template: dict) -> None:
    repo = Path(__file__).parent.parent
    scripts_dir = repo / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from seed_sfh_gynae_2ww_template import build_payload

    payload = build_payload()
    assert payload["organization_id"] == template["organization_id"]
    assert payload["service_id"] == template["service_id"]
    assert payload["organization_name"] == template["organization_name"]
    assert payload["service_name"] == template["service_name"]


def test_section_count(template: dict) -> None:
    assert len(template["sections"]) == 9


def test_all_section_ids_present(sections_by_id: dict) -> None:
    missing = EXPECTED_SECTION_IDS - set(sections_by_id)
    assert not missing, f"Missing sections: {missing}"


def test_all_sections_have_start_pattern(template: dict) -> None:
    for sec in template["sections"]:
        assert sec.get(
            "start_pattern"
        ), f"Section {sec['section_id']} has no start_pattern"


def test_every_section_type_is_one_the_normaliser_handles(template: dict) -> None:
    """An unrecognised type makes the checkbox control a silent no-op."""
    from libs.pipeline.form_schema_section_types import VALID_SECTION_TYPES

    bad = {
        s["section_id"]: s["section_type"]
        for s in template["sections"]
        if s["section_type"] not in VALID_SECTION_TYPES
    }
    assert not bad, f"unrecognised section types: {bad}"


def test_section_a_cancer_types(sections_by_id: dict) -> None:
    sec = sections_by_id["section_a_cancer_type"]
    assert sec["section_type"] == "checkbox_multi"
    patterns = {i["pattern"] for i in sec["items"]}
    missing = CANCER_TYPE_ITEMS - patterns
    assert not missing, f"Section A missing cancer types: {missing}"
    assert "394586005" in sec.get("semantic_tags", [])


def test_section_b_all_nine_items(sections_by_id: dict) -> None:
    sec = sections_by_id["section_b_symptoms"]
    assert sec["section_type"] == "checkbox_yesno"
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
    assert sec["section_type"] == "scale"
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
    coded = {
        cid for member in grp["members"] for cid in (member.get("concept_ids") or [])
    }
    assert {
        _PMB_ID,
        _DISCHARGE_ID,
        _VULVAL_ULCER_ID,
        _VULVAL_MASS_ID,
        _VULVAL_SWELL_ID,
    } <= coded


def test_completeness_symptom_criterion(template: dict) -> None:
    groups = {g["name"]: g for g in template["completeness_groups"]}
    assert "symptom_criterion_required" in groups
    grp = groups["symptom_criterion_required"]
    assert grp["required"] is True
    patterns = {
        str(member.get("item_pattern") or "")
        for member in grp["members"]
        if member.get("item_pattern")
    }
    assert patterns == SYMPTOM_PREFIXES, "All 9 symptom criteria must be in the group"


# NG12 1.5.12 / 1.5.13 / 1.5.14 / 1.5.17 codes that dry-runs already fire.
_PMB_ID = 76742009
_DISCHARGE_ID = 271939006
_VULVAL_ULCER_ID = 68640004
_VULVAL_MASS_ID = 289477004
_VULVAL_SWELL_ID = 289475007


def _groups_from_seed() -> list:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from seed_sfh_gynae_2ww_template import build_completeness_groups

    return build_completeness_groups()


@pytest.mark.parametrize(
    "concept_id",
    [_PMB_ID, _DISCHARGE_ID, _VULVAL_ULCER_ID, _VULVAL_MASS_ID, _VULVAL_SWELL_ID],
)
def test_ng12_gynae_code_satisfies_taught_completeness(concept_id: int) -> None:
    """A present NG12 gynae finding meets both required groups with no ticks.

    Dry-runs 000481827411, 000481858468, 000481914514, 000483240881,
    000484382638, 000486801238: 1.5.12/13/14/17 fired, completeness still
    asked for a Section A/B tick. Same class as breast lump 89164003.
    Atlas: DI-50BE367C / VT-8426C84D
    """
    from libs.completeness.evaluator import evaluate_completeness_groups

    result = evaluate_completeness_groups(
        _groups_from_seed(),
        present_concept_ids={concept_id},
        present_semantic_tags={"finding"},
        section_hits=[],
    )
    names = {row["name"] for row in result["matched_groups"]}
    assert "cancer_type_required" in names, result
    assert "symptom_criterion_required" in names, result
    assert result["complete"] is True
    assert result["degraded"] is False


def test_fixture_completeness_groups_match_seed(template: dict) -> None:
    assert template["completeness_groups"] == _groups_from_seed()


def test_empty_gynae_without_ng12_code_is_still_incomplete() -> None:
    from libs.completeness.evaluator import evaluate_completeness_groups

    result = evaluate_completeness_groups(
        _groups_from_seed(),
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=[],
    )
    missing = {row["name"] for row in result["missing_groups"]}
    assert "cancer_type_required" in missing
    assert "symptom_criterion_required" in missing
    assert result["complete"] is False


def test_no_pii_in_fixture(template: dict) -> None:
    raw = json.dumps(template)
    for token in ("[NAME]", "[NHS_NUMBER]", "[DOB]", "[PHONE]", "[ADDRESS]", "[UBRN]"):
        assert token not in raw, f"PII token {token!r} found in fixture"
