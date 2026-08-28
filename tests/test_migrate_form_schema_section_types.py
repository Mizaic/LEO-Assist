"""Guard the section-type repair migration.

The migration rewrites production form schemas, so its planning and its
safety checks are tested without touching a graph. Every assertion here is
about the pure functions: what the plan changes, what it refuses to change,
and that a second run is a no-op.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from libs.pipeline.form_schema_section_types import is_valid_section_type

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts/migrate_form_schema_section_types.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_migrate_section_types", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


def _production_sections() -> list[dict[str, object]]:
    """The Sherwood schema as production stores it, five sections broken."""
    broken = {
        "section_a_cancer_type",
        "section_b_symptoms",
        "primary_care_pathway",
        "patient_awareness",
        "section_e_performance",
    }
    sections: list[dict[str, object]] = []
    for section_id in [
        "section_a_cancer_type",
        "section_b_symptoms",
        "primary_care_pathway",
        "patient_awareness",
        "section_c_clinical_details",
        "section_d_investigations",
        "section_e_performance",
    ]:
        sections.append(
            {
                "section_id": section_id,
                "section_type": "checkbox" if section_id in broken else "free_text",
                "label": section_id.replace("_", " ").title(),
                "start_pattern": section_id[:9],
                "items": [{"item_id": f"{section_id}_1", "label": "An item"}],
                "semantic_tags": ["gynae"],
            }
        )
    return sections


def test_plan_fixes_every_broken_section_and_leaves_valid_ones() -> None:
    sections = _production_sections()

    planned, changes = migration._planned_sections(sections)

    assert {c[0] for c in changes} == {
        "section_a_cancer_type",
        "section_b_symptoms",
        "primary_care_pathway",
        "patient_awareness",
        "section_e_performance",
    }
    assert all(c[1] == "checkbox" for c in changes)
    assert all(is_valid_section_type(str(s["section_type"])) for s in planned)


def test_plan_maps_each_section_to_the_type_the_referral_text_needs() -> None:
    planned, _ = migration._planned_sections(_production_sections())
    by_id = {s["section_id"]: s["section_type"] for s in planned}

    assert by_id["section_a_cancer_type"] == "checkbox_multi"
    assert by_id["section_b_symptoms"] == "checkbox_yesno"
    assert by_id["primary_care_pathway"] == "checkbox_yesno"
    assert by_id["patient_awareness"] == "checkbox_yesno"
    assert by_id["section_e_performance"] == "scale"
    assert by_id["section_c_clinical_details"] == "free_text"


def test_plan_touches_nothing_but_the_section_type() -> None:
    sections = _production_sections()

    planned, _ = migration._planned_sections(sections)

    for old, new in zip(sections, planned):
        assert old["items"] == new["items"]
        assert old["label"] == new["label"]
        assert old["start_pattern"] == new["start_pattern"]
        assert old["semantic_tags"] == new["semantic_tags"]


def test_second_run_is_a_no_op() -> None:
    planned, _ = migration._planned_sections(_production_sections())

    replanned, changes = migration._planned_sections(planned)

    assert changes == []
    assert replanned == planned


def test_plan_stops_on_an_unmapped_bad_type_rather_than_guessing() -> None:
    sections = [{"section_id": "mystery_section", "section_type": "tickbox"}]

    with pytest.raises(migration.MigrationError) as excinfo:
        migration._planned_sections(sections)

    assert "mystery_section" in str(excinfo.value)
    assert "tickbox" in str(excinfo.value)


def test_write_guard_rejects_a_changed_label() -> None:
    before = [{"section_id": "a", "section_type": "checkbox_multi", "label": "A"}]
    after = [{"section_id": "a", "section_type": "checkbox_multi", "label": "B"}]

    with pytest.raises(migration.MigrationError) as excinfo:
        migration._assert_only_section_types_changed(before, after)

    assert "label" in str(excinfo.value)


def test_write_guard_rejects_a_dropped_section() -> None:
    before = [{"section_id": "a"}, {"section_id": "b"}]

    with pytest.raises(migration.MigrationError):
        migration._assert_only_section_types_changed(before, [{"section_id": "a"}])


def test_write_guard_rejects_a_dropped_field() -> None:
    before = [{"section_id": "a", "section_type": "scale", "items": []}]
    after = [{"section_id": "a", "section_type": "scale"}]

    with pytest.raises(migration.MigrationError):
        migration._assert_only_section_types_changed(before, after)


def test_property_guard_rejects_an_unexpected_property_change() -> None:
    before = {"sections_json": "[]", "org_id": "RK5"}
    after = {"sections_json": "[1]", "org_id": "RK9"}

    with pytest.raises(migration.MigrationError) as excinfo:
        migration._report_unchanged_properties(before, after)

    assert "org_id" in str(excinfo.value)


def test_property_guard_allows_sections_json_and_updated_at() -> None:
    before = {"sections_json": "[]", "updated_at": "then", "org_id": "RK5"}
    after = {"sections_json": "[1]", "updated_at": "now", "org_id": "RK5"}

    migration._report_unchanged_properties(before, after)


def test_seed_fixture_already_matches_the_migration_target() -> None:
    """The seeded template and the migration must not disagree."""
    fixture = json.loads(
        (
            _REPO_ROOT / "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
        ).read_text(encoding="ascii")
    )
    sections = fixture if isinstance(fixture, list) else fixture["sections"]
    by_id = {s["section_id"]: s["section_type"] for s in sections}

    for section_id, wanted in migration.SECTION_TYPE_FIXES.items():
        assert by_id[section_id] == wanted
