"""Tests for RULE_FIRED chained rule evaluation.

Atlas trace: VT-945821A7 / DI-8899D4F3 / DO-274E5A61
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub pyroaring before any evaluation module is imported.
# pyroaring is a C extension that requires the terminology_api virtual env;
# for unit testing we only need the set-like membership and intersection ops.
# ---------------------------------------------------------------------------

class _FakeBitMap:
    """Minimal BitMap stub sufficient for unit tests."""

    def __init__(self, values=()):
        self._data: set = set(values)

    def __and__(self, other):
        return _FakeBitMap(self._data & other._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, item):
        return item in self._data

    def issubset(self, other):
        return self._data.issubset(other._data)


_pyroaring_mod = ModuleType("pyroaring")
_pyroaring_mod.BitMap = _FakeBitMap  # type: ignore[attr-defined]
sys.modules.setdefault("pyroaring", _pyroaring_mod)

# Stub redis so bitmap_store can be imported without a live Redis server.
_redis_mod = ModuleType("redis")
_redis_mod.Redis = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("redis", _redis_mod)

# Stub the observation_evaluator so we don't pull in its heavy imports.
_obs_eval_mod = ModuleType(
    "services.terminology_api.app.services.observation_evaluator"
)
_obs_eval_mod.observation_matches = MagicMock(return_value=False)  # type: ignore[attr-defined]
sys.modules.setdefault(
    "services.terminology_api.app.services.observation_evaluator", _obs_eval_mod
)

# We need to import MagicMock before the stubs above (already imported at top).


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> MagicMock:
    store = MagicMock()
    store.get_bitmap.return_value = None
    return store


def _make_evaluator(store=None):
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )
    return GuidelineEvaluator(store=store or _make_store())


def _patient_ctx(age=None, sex=None):
    from services.terminology_api.app.services.guideline_evaluator import (
        _PatientContext,
    )
    return _PatientContext(
        age=age,
        sex=sex,
        observations=None,
        medications=None,
        allergies=None,
        treatments=None,
    )


def _empty_bm():
    return _FakeBitMap()


def _compiled_rule(rule_id: str, always_fires: bool) -> dict[str, Any]:
    """Return a minimal schema-v2 compiled rule."""
    if always_fires:
        # AND with no children: all([]) == True
        logic_tree: dict[str, Any] = {"kind": "AND", "children": []}
    else:
        # Unknown-bitmap CONCEPT leaf: always fail-closed False
        logic_tree = {
            "kind": "CONCEPT",
            "bitmap_id": "__nonexistent__",
            "node_id": f"{rule_id}-leaf",
        }
    return {
        "rule_id": rule_id,
        "name": f"Rule {rule_id}",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": logic_tree,
    }


def _rule_fired_leaf(
    referenced_rule_id: str,
    outcome: str = "fired",
    node_id: str = "rf1",
) -> dict[str, Any]:
    return {
        "kind": "RULE_FIRED",
        "node_id": node_id,
        "referenced_rule_id": referenced_rule_id,
        "outcome": outcome,
        "display_name": f"Rule {referenced_rule_id}",
    }


def _make_session(evaluator, rules: list[dict], ctx=None, bm=None, cache=None):
    from services.terminology_api.app.services.guideline_evaluator import (
        _RuleEvaluationSession,
    )
    rules_by_id = {r["rule_id"]: r for r in rules}
    return _RuleEvaluationSession(
        evaluator=evaluator,
        rules_by_id=rules_by_id,
        patient_bm=bm or _empty_bm(),
        ctx=ctx or _patient_ctx(),
        bitmap_cache=cache or {},
    )


# ---------------------------------------------------------------------------
# _RuleEvaluationSession unit tests
# ---------------------------------------------------------------------------

class TestRuleEvaluationSession:
    def test_evaluate_always_fires_rule(self):
        """Session.evaluate returns True for a rule whose tree always matches."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        session = _make_session(ev, [rule_a])
        assert session.evaluate("rule:A") is True

    def test_evaluate_never_fires_rule(self):
        """Session.evaluate returns False for a rule whose tree never matches."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=False)
        session = _make_session(ev, [rule_a])
        assert session.evaluate("rule:A") is False

    def test_result_is_memoised(self):
        """Each rule is evaluated at most once; result is cached."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        session = _make_session(ev, [rule_a])
        r1 = session.evaluate("rule:A")
        r2 = session.evaluate("rule:A")
        assert r1 is r2 is True
        assert "rule:A" in session._cache

    def test_missing_rule_returns_false_fail_closed(self):
        """Referencing an absent rule_id returns False (fail-closed)."""
        ev = _make_evaluator()
        session = _make_session(ev, [])
        assert session.evaluate("rule:DOES_NOT_EXIST") is False

    def test_circular_dependency_returns_false_no_crash(self):
        """Circular dependency A->B->A: both return False, no exception."""
        ev = _make_evaluator()
        # Rule A: AND[RULE_FIRED(B, fired)]
        rule_a = {
            "rule_id": "rule:A",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:B")],
            },
        }
        rule_b = {
            "rule_id": "rule:B",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:A")],
            },
        }
        session = _make_session(ev, [rule_a, rule_b])
        # Neither should raise; both should return False.
        result_a = session.evaluate("rule:A")
        result_b = session.evaluate("rule:B")
        assert result_a is False
        assert result_b is False


# ---------------------------------------------------------------------------
# RULE_FIRED leaf in _logic_tree_matches
# ---------------------------------------------------------------------------

class TestLogicTreeMatchesRuleFired:
    def _ltm(self, ev, node, session=None):
        """Call _logic_tree_matches with a node and optional session."""
        return ev._logic_tree_matches(
            node,
            _empty_bm(),
            None,
            None,
            session=session,
        )

    def test_rule_fired_outcome_fired_prerequisite_matches(self):
        """RULE_FIRED(outcome=fired) is True when the prerequisite rule fired."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        session = _make_session(ev, [rule_a])
        node = _rule_fired_leaf("rule:A", outcome="fired")
        assert self._ltm(ev, node, session) is True

    def test_rule_fired_outcome_fired_prerequisite_no_match(self):
        """RULE_FIRED(outcome=fired) is False when the prerequisite did not fire."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=False)
        session = _make_session(ev, [rule_a])
        node = _rule_fired_leaf("rule:A", outcome="fired")
        assert self._ltm(ev, node, session) is False

    def test_rule_fired_outcome_not_fired_prerequisite_no_match(self):
        """RULE_FIRED(outcome=not_fired) is True when the prerequisite did NOT fire."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=False)
        session = _make_session(ev, [rule_a])
        node = _rule_fired_leaf("rule:A", outcome="not_fired")
        assert self._ltm(ev, node, session) is True

    def test_rule_fired_outcome_not_fired_prerequisite_matches(self):
        """RULE_FIRED(outcome=not_fired) is False when the prerequisite fired."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        session = _make_session(ev, [rule_a])
        node = _rule_fired_leaf("rule:A", outcome="not_fired")
        assert self._ltm(ev, node, session) is False

    def test_rule_fired_without_session_returns_false(self):
        """RULE_FIRED with no session always returns False (fail-closed)."""
        ev = _make_evaluator()
        node = _rule_fired_leaf("rule:A")
        assert self._ltm(ev, node, session=None) is False


# ---------------------------------------------------------------------------
# Three-deep chain
# ---------------------------------------------------------------------------

class TestThreeDeepChain:
    def test_chain_a_b_c_all_fire(self):
        """A fires, B depends on A (fired), C depends on B (fired) -- all fire."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        rule_b: dict[str, Any] = {
            "rule_id": "rule:B",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:A", outcome="fired")],
            },
        }
        rule_c: dict[str, Any] = {
            "rule_id": "rule:C",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:B", outcome="fired")],
            },
        }
        session = _make_session(ev, [rule_a, rule_b, rule_c])
        assert session.evaluate("rule:A") is True
        assert session.evaluate("rule:B") is True
        assert session.evaluate("rule:C") is True

    def test_chain_c_blocked_when_a_does_not_fire(self):
        """A does not fire -> B does not fire -> C does not fire."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=False)
        rule_b: dict[str, Any] = {
            "rule_id": "rule:B",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:A", outcome="fired")],
            },
        }
        rule_c: dict[str, Any] = {
            "rule_id": "rule:C",
            "schema_version": 2,
            "guideline_id": "NG12",
            "logic_tree": {
                "kind": "AND",
                "children": [_rule_fired_leaf("rule:B", outcome="fired")],
            },
        }
        session = _make_session(ev, [rule_a, rule_b, rule_c])
        assert session.evaluate("rule:C") is False


# ---------------------------------------------------------------------------
# Diagnose path annotation
# ---------------------------------------------------------------------------

class TestAnnotateRuleFired:
    def test_annotate_rule_fired_leaf_appears_in_tree(self):
        """_annotate_logic_tree annotates RULE_FIRED leaves with matched=True/False."""
        ev = _make_evaluator()
        rule_a = _compiled_rule("rule:A", always_fires=True)
        session = _make_session(ev, [rule_a])
        node = {
            "kind": "AND",
            "children": [_rule_fired_leaf("rule:A", outcome="fired", node_id="rf1")],
        }
        annotated = ev._annotate_logic_tree(
            node, _empty_bm(), None, None, session=session
        )
        assert annotated is not None
        assert annotated["matched"] is True
        rf_child = next(
            c for c in annotated["children"] if c["kind"] == "RULE_FIRED"
        )
        assert rf_child["matched"] is True
        assert rf_child["referenced_rule_id"] == "rule:A"
