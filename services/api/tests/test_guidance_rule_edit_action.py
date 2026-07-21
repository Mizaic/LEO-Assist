"""Tests for the editable recommended action(s) on guidance rules.

Covers DI-LEO-AI-170 and DI-42246DA7 (multi-action support):
  - RuleUpdates accepts an optional ``action`` LogicCriterion (legacy,
    singular) and the new ``actions`` list, each with its own strength.
  - Legacy singular ``action``/``strength`` payloads are synthesised
    server-side into a one-item ``actions`` list (back-compat).
  - apply_rule_edit verifies every action's SNOMED concept exists,
    rejects duplicate SNOMED codes across actions, persists the new
    actionJson (as a JSON array) when supplied, and preserves the
    predecessor's actionJson when omitted (no silent null-out path).
  - _format_rule exposes a parsed ``actions`` list (plus a derived
    ``action`` = actions[0]) on every rule response, tolerating both
    the legacy single-object actionJson shape and the new array shape.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.routers.guidance_rules import _format_rule, _parse_actions_json
from app.services.guidance_rule_edit import (
    LogicCriterion,
    LogicTreeValidationError,
    RuleAction,
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


def _action_criterion(
    concept_id: str = "168731009",
    preferred_term: str = "Plain chest X-ray (procedure)",
    term: str = "chest X-ray",
) -> dict:
    return {
        "snomed_concept_id": concept_id,
        "preferred_term": preferred_term,
        "semantic_tag": "procedure",
        "term": term,
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


def _updates_with_actions(actions: list[dict] | None = None) -> RuleUpdates:
    payload = {
        "name": "Edited rule",
        "logic_tree": _and_root(),
    }
    if actions is not None:
        payload["actions"] = actions
    return RuleUpdates.model_validate(payload)


def _pred_row() -> dict:
    return {
        "status": "pending_review",
        "name": "Old",
        "strength": "offer",
        "compile_scope_id": "NG12",
        "recommendation_id": "rec-1",
        "verbatim": "...",
    }


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
        assert updates.actions is None

    def test_legacy_singular_action_is_synthesised_into_actions_list(self) -> None:
        """DI-42246DA7: an old-shape payload still round-trips (back-compat)."""
        updates = _updates_with_action(_action_criterion())
        assert updates.actions is not None
        assert len(updates.actions) == 1
        assert updates.actions[0].criterion.snomed_concept_id == "168731009"
        assert updates.actions[0].strength == "offer"

    def test_accepts_actions_list_directly(self) -> None:
        updates = _updates_with_actions(
            [
                {"criterion": _action_criterion(), "strength": "offer"},
                {
                    "criterion": _action_criterion("166717003", "Full blood count", "FBC"),
                    "strength": "consider",
                },
            ]
        )
        assert updates.actions is not None
        assert len(updates.actions) == 2
        assert updates.actions[0].strength == "offer"
        assert updates.actions[1].criterion.snomed_concept_id == "166717003"
        assert updates.actions[1].strength == "consider"

    def test_action_defaults_strength_to_unspecified(self) -> None:
        action = RuleAction(criterion=LogicCriterion.model_validate(_action_criterion()))
        assert action.strength == "unspecified"


# -- VT-168-TC-002 -----------------------------------------------------------


class TestActionConceptVerification:
    def test_rejects_action_with_unknown_snomed_concept(self) -> None:
        client = _mock_kg_client([
            # 1: predecessor lookup
            [_pred_row()],
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

    def test_verifies_concepts_for_every_action_in_a_multi_action_payload(self) -> None:
        client = _mock_kg_client([
            [_pred_row()],
            [
                {"concept_id": "49727002", "exists": True},
                {"concept_id": "168731009", "exists": True},
                {"concept_id": "166717003", "exists": False},
            ],
        ])
        with pytest.raises(LogicTreeValidationError, match="166717003"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:rec-1:old",
                updates=_updates_with_actions(
                    [
                        {"criterion": _action_criterion(), "strength": "offer"},
                        {
                            "criterion": _action_criterion(
                                "166717003", "Full blood count", "FBC"
                            ),
                            "strength": "consider",
                        },
                    ]
                ),
                reviewer="qa-lead",
                reason="Add second procedure",
            )


# -- Duplicate SNOMED code across actions ------------------------------------


class TestDuplicateActionConceptRejected:
    def test_rejects_two_actions_with_the_same_snomed_concept(self) -> None:
        client = _mock_kg_client([[_pred_row()]])
        with pytest.raises(LogicTreeValidationError, match="Duplicate recommended action"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:rec-1:old",
                updates=_updates_with_actions(
                    [
                        {"criterion": _action_criterion(), "strength": "offer"},
                        {"criterion": _action_criterion(), "strength": "refer"},
                    ]
                ),
                reviewer="qa-lead",
                reason="Accidental duplicate",
            )
        # Rejected before even the predecessor/concept-verify round trip.
        assert client.run.call_count == 0


# -- VT-168-TC-003 -----------------------------------------------------------


class TestActionPersistedWhenSupplied:
    def test_insert_call_carries_supplied_action_json_as_array(self) -> None:
        client = _mock_kg_client([
            [_pred_row()],
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
        assert isinstance(decoded, list), "actionJson must persist as a JSON array"
        assert len(decoded) == 1
        assert decoded[0]["snomed_concept_id"] == "168731009"
        assert decoded[0]["preferred_term"] == "Plain chest X-ray (procedure)"
        assert decoded[0]["semantic_tag"] == "procedure"
        assert decoded[0]["strength"] == "offer"

    def test_multi_action_persist_writes_every_action_with_its_own_strength(self) -> None:
        client = _mock_kg_client([
            [_pred_row()],
            [
                {"concept_id": "49727002", "exists": True},
                {"concept_id": "168731009", "exists": True},
                {"concept_id": "166717003", "exists": True},
            ],
            [{"id": "rule:rec-1:old:edit:deadbeef"}],
            [{"rejected_ids": []}],
        ])
        result = apply_rule_edit(
            client,
            predecessor_rule_id="rule:rec-1:old",
            updates=_updates_with_actions(
                [
                    {"criterion": _action_criterion(), "strength": "offer"},
                    {
                        "criterion": _action_criterion(
                            "166717003", "Full blood count", "FBC"
                        ),
                        "strength": "consider",
                    },
                ]
            ),
            reviewer="qa-lead",
            reason="Add second procedure",
        )
        assert result["rule_id"].startswith("rule:rec-1:old:edit:")
        insert_call = client.run.call_args_list[2]
        decoded = json.loads(insert_call.kwargs["action_json"])
        assert len(decoded) == 2
        assert decoded[0]["snomed_concept_id"] == "168731009"
        assert decoded[0]["strength"] == "offer"
        assert decoded[1]["snomed_concept_id"] == "166717003"
        assert decoded[1]["strength"] == "consider"
        # Legacy top-level strength mirrors the first action's strength.
        assert insert_call.kwargs["strength"] == "offer"


# -- VT-168-TC-004 -----------------------------------------------------------


class TestActionPreservedWhenOmitted:
    def test_insert_call_passes_null_action_json_so_coalesce_fires(self) -> None:
        client = _mock_kg_client([
            [_pred_row()],
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


# -- _format_rule + _parse_actions_json (API surface) ------------------------


class TestFormatRuleExposesActions:
    def test_parses_array_shaped_action_json_into_actions_list(self) -> None:
        raw_actions = json.dumps(
            [
                {
                    "term": "chest X-ray",
                    "snomed_concept_id": "168731009",
                    "preferred_term": "Plain chest X-ray (procedure)",
                    "semantic_tag": "procedure",
                    "strength": "offer",
                },
                {
                    "term": "FBC",
                    "snomed_concept_id": "166717003",
                    "preferred_term": "Full blood count",
                    "semantic_tag": "procedure",
                    "strength": "consider",
                },
            ]
        )
        formatted = _format_rule({
            "rule_id": "r1",
            "name": "Test",
            "status": "pending_review",
            "strength": "offer",
            "schema_version": 2,
            "logic_json": json.dumps({"kind": "AND", "children": []}),
            "action_json": raw_actions,
            "criteria": [],
        })
        assert len(formatted["actions"]) == 2
        assert formatted["actions"][0]["criterion"]["snomed_concept_id"] == "168731009"
        assert formatted["actions"][0]["strength"] == "offer"
        assert formatted["actions"][1]["criterion"]["snomed_concept_id"] == "166717003"
        assert formatted["actions"][1]["strength"] == "consider"
        # Legacy derived field mirrors the first action's flat criterion.
        assert formatted["action"] == formatted["actions"][0]["criterion"]

    def test_parses_legacy_single_object_action_json_into_one_item_list(self) -> None:
        """Old rows (single JSON object, no array) need no backfill."""
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
        assert formatted["actions"] == [
            {
                "criterion": {
                    "snomed_concept_id": "168731009",
                    "preferred_term": "Plain chest X-ray (procedure)",
                    "semantic_tag": "procedure",
                    "term": "chest X-ray",
                },
                "strength": "unspecified",
            }
        ]
        assert formatted["action"] == formatted["actions"][0]["criterion"]

    def test_actions_is_empty_list_when_action_json_missing(self) -> None:
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
        assert formatted["actions"] == []
        assert formatted["action"] is None

    def test_parse_actions_json_handles_malformed_input(self) -> None:
        # Garbage in -> ``[]`` out, never an exception. Defends the
        # API surface against any historical actionJson rows that have
        # bad shapes from earlier prompt versions.
        assert _parse_actions_json("not json at all") == []
        assert _parse_actions_json("") == []
        assert _parse_actions_json("42") == []

    def test_parse_actions_json_accepts_an_empty_array(self) -> None:
        # An empty array is a valid (if unusual) "no actions" shape now
        # that arrays are the canonical representation.
        assert _parse_actions_json("[]") == []
