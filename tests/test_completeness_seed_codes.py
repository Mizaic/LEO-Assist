"""Completeness seed groups must carry SNOMED codes or semantic tags.

A name-only group cannot be matched against extracted facts by the evaluator,
which compares concept_ids and semantic_categories only. Seeded groups for
well-known clinical requirements must be matchable out of the box.

Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
"""

from __future__ import annotations

from libs.pipeline.form_completeness_seed import seed_completeness_groups
from libs.pipeline.form_section_splitter import split_form_sections

SHERWOOD = """
Sherwood Forest Hospitals NHS Foundation Trust
URGENT SUSPECTED CANCER REFERRAL FOR SUSPECTED GYNAECOLOGICAL MALIGNANCY

Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]
IF endometrium MUST TVUS. IF ovary MUST Ca125.

Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]

Section C: Further Clinical details
BMI: 20.2

Section D: Investigations performed
MANDATORY tests: FBC LFTs UEs Calcium
BLOODS DONE TODAY

Minimum Dataset
BP 140/80
HR 70
"""


def _groups():
    sections = split_form_sections(SHERWOOD)
    return seed_completeness_groups(SHERWOOD, sections)


def _find(groups, name_fragment):
    return next((g for g in groups if name_fragment.lower() in g["name"].lower()), None)


def test_blood_pressure_group_has_concept_id_or_semantic_tag():
    """Blood pressure group must be matchable by evaluator."""
    g = _find(_groups(), "blood pressure")
    assert g is not None, "Expected a Blood pressure group"
    has_code = bool(g.get("concept_ids"))
    has_tag = bool(g.get("semantic_categories"))
    assert (
        has_code or has_tag
    ), f"Blood pressure group has no concept_ids or semantic_categories: {g}"


def test_heart_rate_group_has_concept_id_or_semantic_tag():
    g = _find(_groups(), "heart rate")
    assert g is not None, "Expected a Heart rate group"
    has_code = bool(g.get("concept_ids"))
    has_tag = bool(g.get("semantic_categories"))
    assert (
        has_code or has_tag
    ), f"Heart rate group has no concept_ids or semantic_categories: {g}"


def test_tvus_then_arm_has_concept_id_or_semantic_tag():
    """The TVUS then-arm must be matchable."""
    g = _find(_groups(), "Endometrium")
    assert g is not None, "Expected an if-then Endometrium group"
    then_arm = g.get("then_group") or {}
    has_code = bool(then_arm.get("concept_ids"))
    has_tag = bool(then_arm.get("semantic_categories"))
    assert (
        has_code or has_tag
    ), f"TVUS then-arm has no concept_ids or semantic_categories: {then_arm}"


def test_ca125_then_arm_has_concept_id_or_semantic_tag():
    """The Ca125 then-arm must be matchable."""
    g = _find(_groups(), "Ovary")
    assert g is not None, "Expected an if-then Ovary group"
    then_arm = g.get("then_group") or {}
    has_code = bool(then_arm.get("concept_ids"))
    has_tag = bool(then_arm.get("semantic_categories"))
    assert (
        has_code or has_tag
    ), f"Ca125 then-arm has no concept_ids or semantic_categories: {then_arm}"


def test_section_d_bloods_members_have_codes():
    """Universal blood-panel members must be matchable."""
    g = _find(_groups(), "mandatory bloods")
    assert g is not None, "Expected a Section D mandatory bloods group"
    members = {m["name"].lower(): m for m in g.get("members") or []}
    for name in ("fbc", "lft", "ue", "calcium"):
        member = members.get(name)
        assert member is not None, f"Expected member {name}"
        assert member.get("concept_ids") or member.get(
            "semantic_categories"
        ), f"{name} member has no codes: {member}"


def test_section_a_sites_have_no_form_specific_codes():
    """Cancer-site members stay as names so the UI can attach codes per form."""
    g = _find(_groups(), "suspected sites")
    assert g is not None, "Expected a Section A suspected sites group"
    cervix = next(
        (m for m in g.get("members") or [] if m["name"].lower() == "cervix"), None
    )
    assert cervix is not None, "Expected a Cervix member"
    assert not cervix.get(
        "concept_ids"
    ), f"Cervix must not carry a hardcoded concept id: {cervix}"


def test_evaluator_matches_blood_pressure_entity():
    """A BP entity with the right concept ID must satisfy the group."""
    from libs.completeness.evaluator import evaluate_completeness_groups

    groups = _groups()
    bp = _find(groups, "blood pressure")
    assert bp is not None
    result = evaluate_completeness_groups(
        [bp],
        present_concept_ids=set(bp["concept_ids"]) if bp.get("concept_ids") else set(),
        present_semantic_tags=set(bp.get("semantic_categories") or []),
    )
    assert (
        result["complete"] is True
    ), f"BP group not matched. missing={result['missing_groups']}"
