"""VT-LEO-AI-175 -- sandbox compile + 'no ruleset compiled' signalling.

Covers:

- ``GuidelineCompiler.compile_drafts`` writes draft rules into a custom
  scope using the same per-leaf bitmap flow as the production compile
  (parity with ``_compile_schema_v2_rule``).
- The compiler refuses ``scope_type='global'`` so a draft can never
  collide with the production ruleset.
- ``BitmapStore.delete_scope`` removes only the requested sandbox keys
  and refuses to delete the global production scope.
- ``GuidelineEvaluator.evaluate_patient`` and ``.diagnose`` surface a
  ``not_compiled`` flag (plus a ``recompile_hint``) when no active
  ruleset exists for the requested scope, so the UI can render a loud
  banner instead of silently treating zero matches as a clean run.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_compiler import (
    CompileScope,
    GuidelineCompiler,
)
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _draft_rule(
    rule_id: str = "draft-rule-1",
    concept_id: str = "443416000",
) -> dict:
    """Return a UI-shaped draft v2 rule with one CONCEPT leaf."""
    return {
        "rule_id": rule_id,
        "name": "Draft rule",
        "strength": "consider",
        "guideline_id": "NG151",
        "guideline_title": "Bowel cancer",
        "recommendation_verbatim": "Refer for rectal bleeding.",
        "logic_tree": {
            "kind": "concept",
            "node_id": "n1",
            "criterion": {
                "snomed_concept_id": concept_id,
                "preferred_term": "Rectal bleeding",
                "term": "Rectal bleeding",
                "distance_child": 0,
                "distance_parent": 0,
            },
        },
        "action": None,
    }


@pytest.fixture()
def store() -> MagicMock:
    s = MagicMock(spec=BitmapStore)
    s.get_or_assign_int_id.side_effect = lambda cid: int(str(cid)[-4:] or 0)
    s.put_bitmap.return_value = "bm-abc"
    s.write_ruleset = MagicMock()
    s.set_current_version = MagicMock()
    s.set_scope_ttl = MagicMock(return_value=2)
    return s


@pytest.fixture()
def compiler(store) -> GuidelineCompiler:
    return GuidelineCompiler(store=store)


@pytest.fixture(autouse=True)
def _stub_kg_driver():
    """Avoid touching a real Neo4j during the compile parity test.

    ``compile_drafts`` opens its own session via ``_kg_driver()``; we
    stub that to a session that returns empty closure rows so
    ``_closure_ids`` falls back to the target concept.
    """
    fake_session = MagicMock()
    fake_session.run.return_value = []
    fake_session.__enter__ = lambda self: self
    fake_session.__exit__ = lambda *a, **k: False
    fake_driver = MagicMock()
    fake_driver.session.return_value = fake_session
    fake_driver.close = MagicMock()
    with patch(
        "services.terminology_api.app.services.guideline_compiler._kg_driver",
        return_value=fake_driver,
    ):
        yield


# ---------------------------------------------------------------------------
# compile_drafts
# ---------------------------------------------------------------------------


class TestCompileDrafts:
    def test_writes_to_custom_scope(self, compiler, store):
        scope = CompileScope.from_values("custom", "draft-test-1")
        summary = asyncio.run(
            compiler.compile_drafts(
                "draft-v1",
                [_draft_rule()],
                scope=scope,
                ttl_seconds=600,
            )
        )
        assert summary["draft"] is True
        assert summary["scope_type"] == "custom"
        assert summary["scope_id"] == "draft-test-1"
        assert summary["rule_count"] == 1
        store.write_ruleset.assert_called_once()
        kwargs = store.write_ruleset.call_args.kwargs
        assert kwargs["scope_type"] == "custom"
        assert kwargs["scope_id"] == "draft-test-1"
        # The active-version pointer for the sandbox must be set so a
        # follow-up evaluate against scope=custom/draft-test-1 finds it.
        store.set_current_version.assert_called_once_with(
            "draft-v1", scope_type="custom", scope_id="draft-test-1"
        )
        store.set_scope_ttl.assert_called_once_with(
            "custom", "draft-test-1", ttl_seconds=600
        )

    def test_refuses_global_scope(self, compiler):
        with pytest.raises(ValueError, match="global"):
            asyncio.run(
                compiler.compile_drafts(
                    "draft-v2",
                    [_draft_rule()],
                    scope=CompileScope("global", "default"),
                )
            )

    def test_logic_tree_string_payload_is_accepted(self, compiler, store):
        rule = _draft_rule()
        rule["logic_tree"] = json.dumps(rule["logic_tree"])
        summary = asyncio.run(
            compiler.compile_drafts(
                "draft-v3",
                [rule],
                scope=CompileScope("custom", "from-string"),
            )
        )
        assert summary["rule_count"] == 1

    def test_skips_rules_with_no_logic(self, compiler, store):
        bad = _draft_rule()
        bad.pop("logic_tree")
        summary = asyncio.run(
            compiler.compile_drafts(
                "draft-v4",
                [bad, _draft_rule(rule_id="draft-rule-keep")],
                scope=CompileScope("custom", "skip-test"),
            )
        )
        assert summary["draft_input_count"] == 2
        assert summary["rule_count"] == 1


# ---------------------------------------------------------------------------
# BitmapStore.delete_scope
# ---------------------------------------------------------------------------


class TestDeleteScope:
    def test_refuses_global(self):
        s = BitmapStore()
        with patch.object(s, "_client") as _client:
            _client.return_value = MagicMock()
            with pytest.raises(ValueError, match="global"):
                s.delete_scope("global", "default")

    def test_deletes_keys_for_custom_scope(self):
        s = BitmapStore()
        client = MagicMock()
        client.keys.return_value = [
            b"ruleset:custom:sandbox-1:draft-1",
            b"ruleset:custom:sandbox-1:draft-2",
        ]
        client.delete.return_value = 3
        with patch.object(s, "_client", return_value=client):
            removed = s.delete_scope("custom", "sandbox-1")
        assert removed == 3
        # The current-version pointer key must be included in the delete
        # call so the evaluator stops returning the stale ruleset.
        deleted_keys = [
            k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
            for k in client.delete.call_args.args
        ]
        assert any("current" in k for k in deleted_keys)


# ---------------------------------------------------------------------------
# Evaluator -- not_compiled signalling
# ---------------------------------------------------------------------------


class TestEvaluatorNotCompiled:
    def test_evaluate_patient_marks_not_compiled(self):
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = None
        evaluator = GuidelineEvaluator(store=store)
        result = evaluator.evaluate_patient(
            ["443416000"], scope_type="global", scope_id="default"
        )
        assert result["not_compiled"] is True
        assert result["matched_rules"] == []
        assert "compile" in (result.get("recompile_hint") or "").lower()

    def test_evaluate_patient_marks_compiled_false_on_success(self):
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = {
            "version": "v1",
            "scope_type": "global",
            "scope_id": "default",
            "rules": [],
        }
        store.get_int_id.return_value = None
        evaluator = GuidelineEvaluator(store=store)
        result = evaluator.evaluate_patient(["443416000"])
        assert result["not_compiled"] is False
        assert result["active_version"] == "v1"

    def test_diagnose_returns_structured_not_compiled(self):
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = None
        evaluator = GuidelineEvaluator(store=store)
        result = evaluator.diagnose("rule-x", ["443416000"])
        assert result is not None
        assert result["not_compiled"] is True
        assert result["rule_found"] is False
        assert result["fires"] is False

    def test_diagnose_returns_rule_not_found(self):
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = {
            "version": "v1",
            "scope_type": "global",
            "scope_id": "default",
            "rules": [{"rule_id": "other-rule"}],
        }
        store.get_int_id.return_value = None
        evaluator = GuidelineEvaluator(store=store)
        result = evaluator.diagnose("rule-x", ["443416000"])
        assert result["not_compiled"] is False
        assert result["rule_found"] is False
        assert result["active_version"] == "v1"
