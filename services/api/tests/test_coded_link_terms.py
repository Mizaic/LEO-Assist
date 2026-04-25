"""Regression coverage for coded-link display projection."""

from pathlib import Path

from libs.cypher.documents_queries import LIST_ENCOUNTER_CODED_LINKS

REPO_ROOT = Path(__file__).resolve().parents[3]
PATIENTS_ROUTER = REPO_ROOT / "services/api/app/routers/patients.py"


def test_coded_link_query_uses_name_or_term_for_display_label() -> None:
    """2WW deterministic writes store the preferred term on ``Concept.term``."""

    assert "coalesce(s.name, s.term) AS term" in LIST_ENCOUNTER_CODED_LINKS


def test_coded_link_router_hydrates_existing_observable_measurements() -> None:
    src = PATIENTS_ROUTER.read_text(encoding="utf-8")

    assert "_hydrate_observable_measurement(row)" in src
    assert "detect_lab_pattern(evidence)" in src
    assert 'row["value"] = pattern.numeric_value' in src
    assert 'row["unit"] = pattern.unit' in src
