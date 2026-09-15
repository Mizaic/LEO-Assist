"""Tests for include_rule_ids filter in GuidelineCompiler.

VT: covers DI-8DD23CE2 (compile scope/filter extension).

TC-001: include_rule_ids=None emits all active rules (backwards compat).
TC-002: include_rule_ids with one ID emits only that rule.
TC-003: include_rule_ids=[] compiles to zero rules.
TC-004: _build_fetch_*_query adds IN filter when include_rule_ids is set.
TC-005: compile_and_store passes include_rule_ids through to _compile_ruleset.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.terminology_api.app.services.guideline_compiler import (
    CompileScope,
    GuidelineCompiler,
)
from services.terminology_api.app.services.bitmap_store import BitmapStore


def _make_row(rule_id="r1", concept_id="443416000", **kw):
    return {
        "rule_id": rule_id,
        "name": kw.get("name", "Test rule"),
        "strength": "refer",
        "schema_version": 1,
        "logic_json": None,
        "action_json": None,
        "guideline_id": kw.get("guideline_id", "NG12"),
        "guideline_title": "Test guideline",
        "chapter_title": "Chapter",
        "recommendation_verbatim": "Refer.",
        "group_id": f"{rule_id}:PRESENT",
        "group_mode": "ALL",
        "predicate": "PRESENT",
        "concept_id": concept_id,
        "distance_child": 0,
        "distance_parent": 0,
    }


@pytest.fixture()
def store():
    s = MagicMock(spec=BitmapStore)
    s.get_or_assign_int_id.side_effect = lambda cid: hash(cid) % 10000
    s.put_bitmap.return_value = "abc123"
    s.write_ruleset = MagicMock()
    s.set_current_version = MagicMock()
    return s


@pytest.fixture()
def compiler(store):
    return GuidelineCompiler(store=store)


# -- TC-004: Cypher filter --------------------------------------------------


def test_build_fetch_rules_query_no_filter_by_default(compiler):
    """TC-004a: when include_rule_ids is None, no IN clause is added."""
    scope = CompileScope(scope_type="global", scope_id="default")
    query = compiler._build_fetch_active_rules_query(
        scope, include_rule_ids=None
    )
    assert "rule.id IN" not in query


def test_build_fetch_rules_query_adds_in_filter(compiler):
    """TC-004b: when include_rule_ids is set, IN clause is present."""
    scope = CompileScope(scope_type="global", scope_id="default")
    query = compiler._build_fetch_active_rules_query(
        scope, include_rule_ids=["r1", "r2"]
    )
    assert "rule.id IN $rule_ids" in query


def test_build_fetch_applies_to_query_adds_in_filter(compiler):
    """TC-004c: applies_to query also gains IN filter."""
    scope = CompileScope(scope_type="global", scope_id="default")
    query = compiler._build_fetch_applies_to_query(
        scope, include_rule_ids=["r1"]
    )
    assert "rule.id IN $rule_ids" in query


def test_build_fetch_actions_query_adds_in_filter(compiler):
    """TC-004d: actions query also gains IN filter."""
    scope = CompileScope(scope_type="global", scope_id="default")
    query = compiler._build_fetch_actions_query(
        scope, include_rule_ids=["r1"]
    )
    assert "rule.id IN $rule_ids" in query


# -- TC-001/002/003: end-to-end compile_and_store ---------------------------


def _neo4j_rows(rule_ids):
    """Return rows only for the given rule IDs."""
    return [_make_row(rule_id=rid) for rid in rule_ids]


def _make_compile_mocks(rule_ids_in_db):
    """Patch KG driver so compile sees the given rule rows on the first call."""
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)

    call_count = [0]

    def _run(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return iter(_neo4j_rows(rule_ids_in_db))
        return iter([])

    session.run.side_effect = _run
    driver = MagicMock()
    driver.session.return_value = session
    return driver


@pytest.mark.asyncio
async def test_none_include_rule_ids_emits_all(compiler):
    """TC-001: include_rule_ids=None compiles all rows returned by Neo4j."""
    driver = _make_compile_mocks(["r1", "r2", "r3"])
    with patch(
        "services.terminology_api.app.services.guideline_compiler._kg_driver",
        return_value=driver,
    ):
        result = await compiler.compile_and_store(
            "v-test-001",
            scope=CompileScope("global", "default"),
            include_rule_ids=None,
        )
    assert result["rule_count"] == 3


@pytest.mark.asyncio
async def test_include_rule_ids_filters_to_subset(compiler):
    """TC-002: include_rule_ids=["r1"] emits only r1 even when DB has r1+r2."""
    driver = _make_compile_mocks(["r1", "r2"])
    with patch(
        "services.terminology_api.app.services.guideline_compiler._kg_driver",
        return_value=driver,
    ):
        result = await compiler.compile_and_store(
            "v-test-002",
            scope=CompileScope("custom", "lower-gi"),
            include_rule_ids=["r1"],
        )
    assert result["rule_count"] == 1


@pytest.mark.asyncio
async def test_empty_include_rule_ids_compiles_zero(compiler):
    """TC-003: include_rule_ids=[] produces zero rules."""
    driver = _make_compile_mocks(["r1", "r2"])
    with patch(
        "services.terminology_api.app.services.guideline_compiler._kg_driver",
        return_value=driver,
    ):
        result = await compiler.compile_and_store(
            "v-test-003",
            scope=CompileScope("custom", "empty-set"),
            include_rule_ids=[],
        )
    assert result["rule_count"] == 0
