"""Tests for idempotent org-type backfill labelling rules."""

from __future__ import annotations

from scripts.backfill_org_types import (
    CYPHER_FIND_GP_CANDIDATES,
    CYPHER_FIND_SP_CANDIDATES,
    plan_relabels,
)


def test_find_queries_use_correct_relationships() -> None:
    assert "HAS_GENERAL_PRACTITIONER" in CYPHER_FIND_GP_CANDIDATES
    assert "PROVIDES_SERVICE" in CYPHER_FIND_SP_CANDIDATES
    assert "PROVIDES_SERVICE_FOR" not in CYPHER_FIND_SP_CANDIDATES
    assert "NOT o:GPPractice" in CYPHER_FIND_GP_CANDIDATES
    assert "NOT o:ServiceProvider" in CYPHER_FIND_SP_CANDIDATES


def test_plan_relabels_separates_gp_and_sp() -> None:
    gp_rows = [{"id": "D83007", "name": "Ixworth"}]
    sp_rows = [{"id": "M0L1I", "name": "Trust"}]
    plan = plan_relabels(gp_rows, sp_rows)
    assert plan["gp"] == ["D83007"]
    assert plan["service_provider"] == ["M0L1I"]
    assert plan["counts"] == {"gp": 1, "service_provider": 1}
