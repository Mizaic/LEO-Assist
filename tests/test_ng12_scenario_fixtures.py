"""Schema and pairing validation for NG12 scenario JSON fixtures (348 rows)."""

from __future__ import annotations

import pathlib

import pytest

from tests.helpers.ng12_scenario_loader import (
    iter_paired_rows,
    load_paired_scenarios,
    validate_fixture_pairing,
)

_LOADED_TRIPLES = iter_paired_rows()


def test_ng12_fixture_pairing_and_keys() -> None:
    """Three files align one-for-one and required keys exist."""
    gdl, ext, sbr = load_paired_scenarios()
    validate_fixture_pairing(gdl, ext, sbr)
    assert gdl["_meta"].get("guideline_id") == "NG12"
    assert ext["_meta"]["branch_total"] == 348
    assert len(gdl["scenarios"]) == 348


def test_exemplar_row_has_optional_schema_fields() -> None:
    """Exemplar row carries surface_forms on EXT and _graph_status on GDL."""
    gdl, ext, sbr = load_paired_scenarios()
    grow = next(s for s in gdl["scenarios"] if s["id"] == "NG12-GDL-100")
    erow = next(s for s in ext["scenarios"] if s["id"] == "NG12-EXT-100")
    assert "_graph_status" in grow
    assert grow["_graph_status"] in ("active", "pending_review", "not_coded")
    assert isinstance(erow.get("surface_forms_in_graph"), list)
    assert "expected_entities" in erow
    assert isinstance(erow["expected_entities"], list)


@pytest.mark.parametrize(
    "grow, erow, srow",
    _LOADED_TRIPLES,
    ids=[t[0]["id"] for t in _LOADED_TRIPLES],
)
def test_parametrised_loader_triple_alignment(
    grow: dict, erow: dict, srow: dict
) -> None:
    """Each GDL/EXT/SBR triple shares rec metadata (348-row loader guard)."""
    assert grow["rec_id"] == erow["rec_id"] == srow["rec_id"]
    assert grow["branch_index"] == erow["branch_index"] == srow["branch_index"]
    assert "encounter_note" in erow
    assert "situation_md" in srow


def test_branches_use_ascii_only() -> None:
    """Committed fixture text must stay ASCII (project policy)."""
    base = pathlib.Path(__file__).resolve().parent / "fixtures" / "ng12_scenarios"
    for fname in (
        "ng12_guideline_scenarios.json",
        "ng12_extraction_scenarios.json",
        "ng12_sbar_scenarios.json",
    ):
        text = (base / fname).read_text(encoding="utf-8")
        text.encode("ascii")
