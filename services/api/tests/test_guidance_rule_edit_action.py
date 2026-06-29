"""Tests for the editable SNOMED action on guidance rules -- VT-LEO-AI-168.

Covers DI-LEO-AI-170:
  - RuleUpdates accepts an optional ``action`` LogicCriterion.
  - apply_rule_edit verifies the action's SNOMED concept exists, persists
    the new actionJson when supplied, and preserves the predecessor's
    actionJson when omitted (no silent null-out path).
  - _format_rule exposes a parsed ``action`` field on every rule
    response.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.routers.guidance_rules import _format_rule, _parse_action_json
from app.services.guidance_rule_edit import (
    LogicCriterion,
    LogicTreeValidationError,
    RuleUpdates,
    apply_rule_edit,
)


# -- helpers -----------------------------------------------------------------


def _concept_node(concept_id: str = "49727002", term: str = "Cough") -> dict:
    return {
        "kind": "CONCEPT",
        "criterion": {
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "semantic_tag": "finding",
        },
    }


def _and_root() -> dict:
    return {"kind": "AND", "children": [_concept_node()]}


def _mock_kg_client(run_results: list) -> MagicMock:
    client = MagicMock()
    client.run.side_effect = run_results
    client.close = MagicMock()
    return client


def _action_criterion() -> dict:
    return {
        "snomed_concept_id": "168731009",
        "preferred_term": "Plain chest X-ray (procedure)",
        "semantic_tag": "procedure",
        "term": "chest X-ray",
    }


def _updates_with_action(action: dict | None = None) -> RuleUpdates:
    payload = {
        "name": "Edited rule",
        "strength": "offer",
        "logic_tree": _and_root(),
    }
    if action is not None:
        payload["action"] = action
    return RuleUpdates.model_validate(payload)


# -- VT-168-TC-001 -----------------------------------------------------------


class TestRuleUpdatesAcceptsAction:
    def test_accepts_optional_action_with_snomed_concept(self) -> None:
        updates = _updates_with_action(_action_criterion())
        assert updates.action is not None
        assert updates.action.snomed_concept_id == "168731009"
        assert updates.action.semantic_tag == "procedure"
        # round-trip through model_dump preserves the SNOMED id
        dumped = updates.model_dump(exclude_none=True)
        assert dumped["action"]["snomed_concept_id"] == "168731009"

    def test_action_is_optional(self) -> None:
        updates = _updates_with_action(None)
        assert updates.action is None


# -- VT-168-TC-002 -----------------------------------------------------------


class TestActionConceptVerification:
    def test_rejects_action_with_unknown_snomed_concept(self) -> None:
        client = _mock_kg_client([
            # 1: predecessor lookup
            [{
                "status": "pending_review",
                "name": "Old",
                "strength": "offer",
                "compile_scope_id": "NG12",
                "recommendation_id": "rec-1",
                "verbatim": "...",
            }],
            # 2: concept verify -- both the logic concept AND the action
            #    concept come back; the action one is missing.
            [
                {"concept_id": "49727002", "exists": True},
                {"concept_id": "168731009", "exists": False},
            ],
        ])
        with pytest.raises(LogicTreeValidationError, match="168731009"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:rec-1:old",
                updates=_updates_with_action(_action_criterion()),
                reviewer="qa-lead",
                reason="Swap procedure",
            )
        # Ensure no INSERT call was made -- we stopped at concept verify.
        assert client.run.call_count == 2


# -- VT-168-TC-003 -----------------------------------------------------------


class TestActionPersistedWhenSupplied:
    def test_insert_call_carries_supplied_action_json(self) -> None:
        client = _mock_kg_client([
            [{
                "status": "pending_review",
                "name": "Old",
                "strength": "offer",
                "compile_scope_id": "NG12",
                "recommendation_id": "rec-1",
                "verbatim": "...",
            }],
            [
                {"concept_id": "49727002", "exists": True},
                {"concept_id": "168731009", "exists": True},
            ],
            [{"id": "rule:rec-1:old:edit:deadbeef"}],
            # 4: reject_sibling_pending_rules
            [{"rejected_ids": []}],
        ])
        apply_rule_edit(
            client,
            predecessor_rule_id="rule:rec-1:old",
            updates=_updates_with_action(_action_criterion()),
            reviewer="qa-lead",
            reason="Swap procedure",
        )
        insert_call = client.run.call_args_list[2]
        action_json = insert_call.kwargs.get("action_json")
        assert action_json is not None, "action_json should be set when reviewer supplies an action"
        decoded = json.loads(action_json)
        assert decoded["snomed_concept_id"] == "168731009"
        assert decoded["preferred_term"] == "Plain chest X-ray (procedure)"
        assert decoded["semantic_tag"] == "procedure"


# -- VT-168-TC-004 -----------------------------------------------------------


class TestActionPreservedWhenOmitted:
    def test_insert_call_passes_null_action_json_so_coalesce_fires(self) -> None:
        client = _mock_kg_client([
            [{
                "status": "pending_review",
                "name": "Old",
                "strength": "offer",
                "compile_scope_id": "NG12",
                "recommendation_id": "rec-1",
                "verbatim": "...",
            }],
            [{"concept_id": "49727002", "exists": True}],
            [{"id": "rule:rec-1:old:edit:deadbeef"}],
            # 4: reject_sibling_pending_rules
            [{"rejected_ids": []}],
        ])
        apply_rule_edit(
            client,
            predecessor_rule_id="rule:rec-1:old",
            updates=_updates_with_action(None),
            reviewer="qa-lead",
            reason="Tweak criteria only",
        )
        insert_call = client.run.call_args_list[2]
        # When the reviewer leaves the action alone we pass None so the
        # COALESCE in _INSERT_EDITED_RULE keeps pred.actionJson intact.
        assert insert_call.kwargs.get("action_json") is None


# -- _format_rule + _parse_action_json (API surface) -------------------------


class TestFormatRuleExposesAction:
    def test_parses_action_json_into_structured_field(self) -> None:
        raw_action = json.dumps({
            "term": "chest X-ray",
            "snomed_concept_id": "168731009",
            "preferred_term": "Plain chest X-ray (procedure)",
            "semantic_tag": "procedure",
        })
        formatted = _format_rule({
            "rule_id": "r1",
            "name": "Test",
            "status": "pending_review",
            "strength": "offer",
            "schema_version": 2,
            "logic_json": json.dumps({"kind": "AND", "children": []}),
            "action_json": raw_action,
            "criteria": [],
        })
        assert formatted["action"] == {
            "snomed_concept_id": "168731009",
            "preferred_term": "Plain chest X-ray (procedure)",
            "semantic_tag": "procedure",
            "term": "chest X-ray",
        }

    def test_action_is_none_when_action_json_missing(self) -> None:
        formatted = _format_rule({
            "rule_id": "r1",
            "name": "Test",
            "status": "pending_review",
            "strength": "offer",
            "schema_version": 2,
            "logic_json": json.dumps({"kind": "AND", "children": []}),
            "action_json": None,
            "criteria": [],
        })
        assert formatted["action"] is None

    def test_parse_action_json_handles_malformed_input(self) -> None:
        # Garbage in -> ``None`` out, never an exception. Defends the
        # API surface against any historical actionJson rows that have
        # bad shapes from earlier prompt versions.
        assert _parse_action_json("not json at all") is None
        assert _parse_action_json("[]") is None  # list, not dict
        assert _parse_action_json("") is None
