"""Tests for GuidelineCompiler -- VT-LEO-AI-065."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from services.terminology_api.app.services.guideline_compiler import (
    CompilePolicy,
    CompileScope,
    GuidelineCompiler,
)
from services.terminology_api.app.services.bitmap_store import BitmapStore


def _make_row(
    rule_id="r1",
    name="Test rule",
    strength="refer",
    guideline_id="NG151",
    guideline_title="Bowel cancer",
    chapter_title="Recommendations",
    group_id="r1:PRESENT",
    group_mode="ALL",
    predicate="PRESENT",
    concept_id="443416000",
    recommendation_verbatim="Refer for rectal bleeding.",
    distance_child=0,
    distance_parent=0,
    action_concept_id=None,
    action_name=None,
    action_priority=None,
    action_due_days=None,
    schema_version=1,
    logic_json=None,
    action_json=None,
):
    return {
        "rule_id": rule_id,
        "name": name,
        "strength": strength,
        "schema_version": schema_version,
        "logic_json": logic_json,
        "action_json": action_json,
        "guideline_id": guideline_id,
        "guideline_title": guideline_title,
        "chapter_title": chapter_title,
        "recommendation_verbatim": recommendation_verbatim,
        "group_id": group_id,
        "group_mode": group_mode,
        "predicate": predicate,
        "concept_id": concept_id,
        "distance_child": distance_child,
        "distance_parent": distance_parent,
        "action_concept_id": action_concept_id,
        "action_name": action_name,
        "action_priority": action_priority,
        "action_due_days": action_due_days,
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


@pytest.fixture()
def mock_session():
    """Neo4j session stub that returns empty closure results."""
    session = MagicMock()
    # No SNOMED IS_A relationships — closure falls back to target only
    session.run.return_value = []
    return session


# ── Cypher contract ──────────────────────────────────────────────────────────


def test_compiler_only_queries_active_rules(compiler):
    """Cypher must filter on status: active to exclude pending_review rules."""
    from services.terminology_api.app.services.guideline_compiler import (
        _FETCH_ACTIVE_RULES,
    )

    assert "status: 'active'" in _FETCH_ACTIVE_RULES


def test_cypher_returns_distance_fields(compiler):
    """Cypher query must return distanceChild and distanceParent from HAS_CRITERIA edge."""
    from services.terminology_api.app.services.guideline_compiler import (
        _FETCH_ACTIVE_RULES,
    )

    assert "distance_child" in _FETCH_ACTIVE_RULES
    assert "distance_parent" in _FETCH_ACTIVE_RULES


def test_cypher_returns_action_fields(compiler):
    """Cypher query must return action priority and due_days from HAS_ACTION edge."""
    from services.terminology_api.app.services.guideline_compiler import (
        _FETCH_ACTIVE_RULES,
    )

    assert "action_priority" in _FETCH_ACTIVE_RULES
    assert "action_due_days" in _FETCH_ACTIVE_RULES
    assert "action_concept_id" in _FETCH_ACTIVE_RULES


def test_scope_query_includes_guideline_filter(compiler):
    query = compiler._build_fetch_active_rules_query(
        CompileScope(scope_type="guideline", scope_id="NG12")
    )
    assert "g.id = $scope_id" in query


def test_scope_query_includes_domain_filter_for_subdomain_scope(compiler):
    query = compiler._build_fetch_active_rules_query(
        CompileScope(scope_type="subdomain", scope_id="cancer_audit:symptoms")
    )
    assert "dom.id = $scope_domain_id" in query


# ── Core compilation ─────────────────────────────────────────────────────────


def test_build_ruleset_groups_present_into_all_group(compiler, store, mock_session):
    """PRESENT criteria compile into a criteria_groups entry with mode=ALL."""
    rows = [_make_row(predicate="PRESENT", group_mode="ALL", concept_id="111")]
    ruleset = compiler._build_ruleset(rows, mock_session)

    assert len(ruleset["rules"]) == 1
    rule = ruleset["rules"][0]
    assert "criteria_groups" in rule
    modes = [g["mode"] for g in rule["criteria_groups"]]
    assert "ALL" in modes


def test_build_ruleset_groups_absent_into_not_group(compiler, store, mock_session):
    """ABSENT criteria (old predicate=ABSENT) compile into mode=NOT group."""
    rows = [
        _make_row(
            predicate="ABSENT",
            group_mode="ANY",  # old data: type=ANY + predicate=ABSENT → NOT
            group_id="r1:ABSENT",
            concept_id="222",
        )
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    modes = [g["mode"] for g in rule["criteria_groups"]]
    assert "NOT" in modes


def test_build_ruleset_handles_multiple_concepts_per_group(
    compiler, store, mock_session
):
    """Multiple concepts in the same group produce one bitmap with all IDs."""
    rows = [
        _make_row(predicate="PRESENT", group_mode="ALL", concept_id="111"),
        _make_row(predicate="PRESENT", group_mode="ALL", concept_id="222"),
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    assert len(ruleset["rules"]) == 1
    store.put_bitmap.assert_called()
    int_ids_used = store.put_bitmap.call_args[0][0]
    assert len(int_ids_used) == 2


def test_build_ruleset_skips_rows_with_no_concept(compiler, store, mock_session):
    """Rows with concept_id = None produce no criteria_groups (rule skipped)."""
    rows = [_make_row(concept_id=None)]
    ruleset = compiler._build_ruleset(rows, mock_session)

    assert len(ruleset["rules"]) == 0


def test_build_ruleset_strict_policy_excludes_out_of_scope_concepts(
    compiler, store, mock_session
):
    rows = [_make_row(predicate="PRESENT", group_mode="ALL", concept_id="111")]
    ruleset = compiler._build_ruleset(
        rows,
        mock_session,
        policy=CompilePolicy(mode="strict", allowed_concept_ids=frozenset({"999"})),
    )
    assert len(ruleset["rules"]) == 0


def test_build_ruleset_advisory_policy_keeps_rule(compiler, store, mock_session):
    rows = [_make_row(predicate="PRESENT", group_mode="ALL", concept_id="111")]
    ruleset = compiler._build_ruleset(
        rows,
        mock_session,
        policy=CompilePolicy(mode="advisory", allowed_concept_ids=frozenset({"999"})),
    )
    assert len(ruleset["rules"]) == 1


def test_build_ruleset_handles_mixed_groups(compiler, store, mock_session):
    """One rule can have both ALL and NOT groups."""
    rows = [
        _make_row(predicate="PRESENT", group_mode="ALL", concept_id="111"),
        _make_row(
            predicate="ABSENT", group_mode="ANY", group_id="r1:ABSENT", concept_id="333"
        ),
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    modes = {g["mode"] for g in rule["criteria_groups"]}
    assert "ALL" in modes
    assert "NOT" in modes  # old ANY+ABSENT converted to NOT


def test_build_ruleset_supports_native_any_mode(compiler, store, mock_session):
    """New-style mode=ANY group (from updated generator) compiles correctly."""
    rows = [
        _make_row(
            predicate="PRESENT",
            group_mode="ANY",
            group_id="r1:PRESENT:0",
            concept_id="444",
        )
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    modes = [g["mode"] for g in rule["criteria_groups"]]
    assert "ANY" in modes


def test_build_ruleset_compiles_schema_v2_logic_tree(compiler, store, mock_session):
    rows = [
        _make_row(
            group_id=None,
            concept_id=None,
            schema_version=2,
            logic_json='{"kind":"AND","children":[{"kind":"concept","criterion":{"node_id":"n1","term":"rectal bleeding","snomed_concept_id":"443416000","preferred_term":"Rectal bleeding","semantic_tag":"finding"}}]}',
        )
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)
    assert len(ruleset["rules"]) == 1
    rule = ruleset["rules"][0]
    assert rule["schema_version"] == 2
    assert rule["logic_tree"]["kind"] == "AND"
    assert rule["logic_tree"]["children"][0]["kind"] == "concept"


# ── SNOMED closure expansion ─────────────────────────────────────────────────


def test_closure_ids_returns_target_when_distances_zero(compiler, mock_session):
    """When distanceChild=0 and distanceParent=0, no IS_A query is made."""
    result = compiler._closure_ids(mock_session, "123456", 0, 0)
    assert result == ["123456"]
    mock_session.run.assert_not_called()


def test_closure_ids_falls_back_gracefully_when_no_is_a_rels(compiler, mock_session):
    """If SNOMED IS_A query returns nothing, closure falls back to target only."""
    mock_session.run.return_value = []
    result = compiler._closure_ids(mock_session, "443416000", 1, 0)
    assert result == ["443416000"]


def test_closure_ids_includes_children_when_is_a_found(compiler, mock_session):
    """When IS_A relationships exist, child concepts are included in closure."""
    mock_session.run.return_value = [
        {"concept_id": "443416000"},
        {"concept_id": "111111001"},  # child concept
    ]
    result = compiler._closure_ids(mock_session, "443416000", 1, 0)
    assert "443416000" in result
    assert "111111001" in result


def test_closure_ids_are_cached(compiler, mock_session):
    """Repeated calls for same concept+distances use the cache, not Neo4j."""
    mock_session.run.return_value = [{"concept_id": "123"}]
    compiler._closure_ids(mock_session, "123", 1, 0)
    compiler._closure_ids(mock_session, "123", 1, 0)
    # Should only query Neo4j once
    assert mock_session.run.call_count == 1


def test_build_ruleset_expands_concept_via_closure(compiler, store, mock_session):
    """distanceChild=1 causes closure lookup and expands to child concepts."""
    # Simulate IS_A returning target + one child
    mock_session.run.return_value = [
        {"concept_id": "443416000"},
        {"concept_id": "child001"},
    ]
    rows = [_make_row(concept_id="443416000", distance_child=1, distance_parent=0)]
    ruleset = compiler._build_ruleset(rows, mock_session)

    # Both the parent and child concept IDs must be mapped to int IDs
    calls = store.get_or_assign_int_id.call_args_list
    coded_ids = {c.args[0] for c in calls}
    assert "443416000" in coded_ids
    assert "child001" in coded_ids


# ── Action metadata ──────────────────────────────────────────────────────────


def test_compiled_rule_includes_action_when_present(compiler, store, mock_session):
    """Compiled rule output contains action dict when HAS_ACTION edge has data."""
    rows = [
        _make_row(
            concept_id="443416000",
            action_concept_id="306206005",
            action_name="Suspected cancer pathway referral",
            action_priority="2ww",
            action_due_days=14,
        )
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    assert rule["action"] is not None
    assert rule["action"]["concept_id"] == "306206005"
    assert rule["action"]["priority"] == "2ww"
    assert rule["action"]["due_days"] == 14


def test_compiled_rule_action_is_none_when_not_present(compiler, store, mock_session):
    """Compiled rule output has action=None when no action was coded."""
    rows = [_make_row(concept_id="443416000")]  # no action fields
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    assert rule["action"] is None


def test_action_backfilled_from_later_rows(compiler, store, mock_session):
    """Action metadata is picked up from any row for the same rule, not just the first."""
    rows = [
        # First row: no action
        _make_row(concept_id="111"),
        # Second row: has action
        _make_row(
            concept_id="222",
            action_concept_id="306206005",
            action_name="Referral",
            action_priority="urgent",
            action_due_days=2,
        ),
    ]
    ruleset = compiler._build_ruleset(rows, mock_session)

    rule = ruleset["rules"][0]
    assert rule["action"] is not None
    assert rule["action"]["priority"] == "urgent"


# ── Async compilation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compile_and_store_writes_version_and_sets_current(compiler, store):
    """compile_and_store writes ruleset and sets active version pointer."""
    with patch.object(compiler, "_compile_ruleset", return_value={"rules": []}):
        summary = await compiler.compile_and_store("v20260308")

    assert summary["version"] == "v20260308"
    store.write_ruleset.assert_called_once()
    store.set_current_version.assert_called_once_with(
        "v20260308", scope_type="global", scope_id="default"
    )


@pytest.mark.asyncio
async def test_compile_and_store_clears_cache_before_run(compiler, store):
    """Closure cache is cleared at the start of each compilation run."""
    compiler._closure_cache["old_key"] = ["old_val"]
    with patch.object(compiler, "_compile_ruleset", return_value={"rules": []}):
        await compiler.compile_and_store("v1")
    # Cache should be cleared before _compile_ruleset ran — the mock means
    # no new entries were added.
    assert len(compiler._closure_cache) == 0


@pytest.mark.asyncio
async def test_compile_and_store_includes_compile_timestamp(compiler, store):
    """compile_and_store adds compile_timestamp to the stored ruleset."""
    with patch.object(compiler, "_compile_ruleset", return_value={"rules": []}):
        summary = await compiler.compile_and_store("v1")

    assert "compile_timestamp" in summary
    assert summary["compile_timestamp"] is not None
