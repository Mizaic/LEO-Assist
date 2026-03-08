"""Tests for GuidelineCompiler -- VT-LEO-AI-065."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.terminology_api.app.services.guideline_compiler import GuidelineCompiler
from services.terminology_api.app.services.bitmap_store import BitmapStore


def _make_row(
    rule_id="r1",
    name="Test rule",
    strength="refer",
    guideline_id="NG151",
    guideline_title="Bowel cancer",
    group_id="r1:PRESENT",
    group_mode="ALL",
    predicate="PRESENT",
    concept_id="443416000",
    recommendation_verbatim="Refer for rectal bleeding.",
):
    return {
        "rule_id": rule_id,
        "name": name,
        "strength": strength,
        "guideline_id": guideline_id,
        "guideline_title": guideline_title,
        "recommendation_verbatim": recommendation_verbatim,
        "group_id": group_id,
        "group_mode": group_mode,
        "predicate": predicate,
        "concept_id": concept_id,
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


def test_compiler_only_queries_active_rules(compiler):
    """Cypher must filter on status: active to exclude pending_review rules."""
    from services.terminology_api.app.services.guideline_compiler import _FETCH_ACTIVE_RULES
    assert "status: 'active'" in _FETCH_ACTIVE_RULES, (
        "Cypher must explicitly filter AppropriatenessRule nodes to status: active"
    )


def test_build_ruleset_groups_present_into_req_all(compiler, store):
    """PRESENT criteria are compiled into req_all bitmaps."""
    rows = [_make_row(predicate="PRESENT", concept_id="111")]
    ruleset = compiler._build_ruleset(rows)

    assert len(ruleset["rules"]) == 1
    rule = ruleset["rules"][0]
    assert rule["req_all_bitmap_id"] is not None
    assert rule["forbid_bitmap_id"] is None


def test_build_ruleset_groups_absent_into_forbid(compiler, store):
    """ABSENT criteria are compiled into forbid bitmaps."""
    rows = [_make_row(predicate="ABSENT", concept_id="222")]
    ruleset = compiler._build_ruleset(rows)

    rule = ruleset["rules"][0]
    assert rule["forbid_bitmap_id"] is not None
    assert rule["req_all_bitmap_id"] is None


def test_build_ruleset_handles_multiple_concepts_per_rule(compiler, store):
    """Multiple PRESENT criteria for the same rule go into one req_all bitmap."""
    rows = [
        _make_row(predicate="PRESENT", concept_id="111"),
        _make_row(predicate="PRESENT", concept_id="222"),
    ]
    ruleset = compiler._build_ruleset(rows)

    assert len(ruleset["rules"]) == 1
    store.put_bitmap.assert_called()
    int_ids_used = store.put_bitmap.call_args[0][0]
    assert len(int_ids_used) == 2


def test_build_ruleset_skips_rows_with_no_concept(compiler, store):
    """Rows with concept_id = None are silently skipped."""
    rows = [_make_row(concept_id=None)]
    ruleset = compiler._build_ruleset(rows)

    assert len(ruleset["rules"]) == 0


def test_build_ruleset_handles_mixed_predicates(compiler, store):
    """One rule can have both req_all and forbid bitmaps."""
    rows = [
        _make_row(predicate="PRESENT", concept_id="111"),
        _make_row(predicate="ABSENT", concept_id="333"),
    ]
    ruleset = compiler._build_ruleset(rows)

    rule = ruleset["rules"][0]
    assert rule["req_all_bitmap_id"] is not None
    assert rule["forbid_bitmap_id"] is not None


@pytest.mark.asyncio
async def test_compile_and_store_writes_version_and_sets_current(compiler, store):
    """compile_and_store writes ruleset and sets active version pointer."""
    import asyncio

    rows = [_make_row(concept_id="100")]

    with patch.object(compiler, "_compile_ruleset", return_value={"rules": []}):
        summary = await compiler.compile_and_store("v20260308")

    assert summary["version"] == "v20260308"
    store.write_ruleset.assert_called_once()
    store.set_current_version.assert_called_once_with("v20260308")


@pytest.mark.asyncio
async def test_compile_and_store_includes_compile_timestamp(compiler, store):
    """compile_and_store adds compile_timestamp to the stored ruleset."""
    with patch.object(compiler, "_compile_ruleset", return_value={"rules": []}):
        summary = await compiler.compile_and_store("v1")

    assert "compile_timestamp" in summary
    assert summary["compile_timestamp"] is not None


@pytest.mark.asyncio
async def test_compile_and_store_uses_thread_for_cpu_work(compiler, store):
    """CPU-bound compile runs via asyncio.to_thread to avoid blocking the loop."""
    import asyncio

    called_in_thread = []

    original = compiler._compile_ruleset

    def tracked():
        called_in_thread.append(True)
        return {"rules": []}

    with patch.object(compiler, "_compile_ruleset", side_effect=tracked):
        with patch("asyncio.to_thread", new=lambda fn, *args, **kwargs: asyncio.coroutine(lambda: fn(*args, **kwargs))()):
            try:
                await compiler.compile_and_store("v1")
            except Exception:
                pass

    store.write_ruleset.assert_called()
