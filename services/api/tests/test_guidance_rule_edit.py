"""Tests for the guidance rule edit pathway -- VT-LEO-AI-152.

Covers:
  - validate_logic_tree: depth/node-count caps, AT_LEAST min vs children,
    NOT arity, missing concept criterion, demographic field/operator rules.
  - apply_rule_edit: writes a new rule, supersedes the predecessor,
    rejects unknown SNOMED concept ids, rejects edits on non-pending rules.
  - Router integration: POST /guidance/rules/review/{id}/decision with an
    ``updates`` payload routes through the edit service and returns the
    new rule_id alongside its predecessor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.guidance_rules import router
from app.services.guidance_rule_edit import (
    EditNotApplicable,
    LogicNode,
    LogicTreeValidationError,
    MAX_NODE_COUNT,
    MAX_TREE_DEPTH,
    RuleUpdates,
    apply_rule_edit,
    validate_logic_tree,
)


# -- Fixtures -----------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    from app import deps

    app.dependency_overrides[deps.require_admin] = lambda: None
    app.include_router(router)
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app())


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
    return {
        "kind": "AND",
        "children": [
            {
                "kind": "DEMOGRAPHIC",
                "field": "age",
                "operator": ">=",
                "value": 40,
                "unit": "years",
            },
            _concept_node(),
        ],
    }


# -- validate_logic_tree -----------------------------------------------------


class TestValidateLogicTree:
    def test_collects_concept_ids_from_well_formed_tree(self) -> None:
        node = LogicNode.model_validate(_and_root())
        ids = validate_logic_tree(node)
        assert ids == {"49727002"}

    def test_rejects_empty_group(self) -> None:
        node = LogicNode.model_validate({"kind": "AND", "children": []})
        with pytest.raises(LogicTreeValidationError, match="at least one child"):
            validate_logic_tree(node)

    def test_rejects_at_least_min_above_child_count(self) -> None:
        node = LogicNode.model_validate({
            "kind": "AT_LEAST",
            "min": 5,
            "children": [_concept_node("1", "A"), _concept_node("2", "B")],
        })
        with pytest.raises(LogicTreeValidationError, match="cannot be greater"):
            validate_logic_tree(node)

    def test_rejects_at_least_min_zero(self) -> None:
        node = LogicNode.model_validate({
            "kind": "AT_LEAST",
            "min": 0,
            "children": [_concept_node()],
        })
        with pytest.raises(LogicTreeValidationError, match="min >= 1"):
            validate_logic_tree(node)

    def test_rejects_not_with_two_children(self) -> None:
        node = LogicNode.model_validate({
            "kind": "NOT",
            "children": [_concept_node("1", "A"), _concept_node("2", "B")],
        })
        with pytest.raises(LogicTreeValidationError, match="exactly one child"):
            validate_logic_tree(node)

    def test_rejects_concept_without_snomed_id(self) -> None:
        with pytest.raises(Exception):
            LogicNode.model_validate(
                {"kind": "CONCEPT", "criterion": {"snomed_concept_id": "", "preferred_term": "x"}}
            )

    def test_rejects_demographic_with_unsupported_field(self) -> None:
        node = LogicNode.model_validate({
            "kind": "DEMOGRAPHIC",
            "field": "weight",
            "operator": ">=",
            "value": 70,
            "unit": "kg",
        })
        with pytest.raises(LogicTreeValidationError, match="unsupported field"):
            validate_logic_tree(node)

    def test_rejects_excessive_depth(self) -> None:
        # Build a chain longer than the cap.
        node: dict = _concept_node()
        for _ in range(MAX_TREE_DEPTH + 1):
            node = {"kind": "AND", "children": [node]}
        with pytest.raises(LogicTreeValidationError, match="max depth"):
            validate_logic_tree(LogicNode.model_validate(node))

    def test_rejects_excessive_node_count(self) -> None:
        children = [_concept_node(str(i), f"c{i}") for i in range(MAX_NODE_COUNT + 5)]
        node = LogicNode.model_validate({"kind": "AND", "children": children})
        with pytest.raises(LogicTreeValidationError, match=f"max allowed is {MAX_NODE_COUNT}"):
            validate_logic_tree(node)

    def test_rejects_unknown_node_kind(self) -> None:
        with pytest.raises(Exception):
            LogicNode.model_validate({"kind": "MAYBE", "children": [_concept_node()]})


# -- Synonym set (UN-LEO-AI-093 / DI-LEO-AI-508) ----------------------------


class TestLogicCriterionSynonymSet:
    """LogicCriterion accepts seeds + exclusions and stays back-compat."""

    def _seed(self, cid: str, term: str, **extra) -> dict:
        return {
            "snomed_concept_id": cid,
            "preferred_term": term,
            "semantic_tag": "finding",
            **extra,
        }

    def test_legacy_single_concept_id_still_validates(self) -> None:
        node = LogicNode.model_validate(_concept_node("1", "Smoker"))
        assert node.criterion.snomed_concept_id == "1"
        assert node.criterion.seeds == []
        assert validate_logic_tree(node) == {"1"}

    def test_seeds_only_payload_derives_legacy_fields(self) -> None:
        """Posting a synonym set without snomed_concept_id derives it from primary."""
        node = LogicNode.model_validate(
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": "",
                    "preferred_term": "",
                    "primary_concept_id": "1",
                    "seeds": [
                        self._seed("1", "Smoker"),
                        self._seed("2", "Cigarette smoker"),
                    ],
                },
            }
        )
        assert node.criterion.snomed_concept_id == "1"
        assert node.criterion.preferred_term == "Smoker"
        assert {s.snomed_concept_id for s in node.criterion.seeds} == {"1", "2"}

    def test_validate_logic_tree_collects_every_seed_and_exclusion_id(self) -> None:
        node = LogicNode.model_validate(
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": "1",
                    "preferred_term": "Smoker",
                    "primary_concept_id": "1",
                    "seeds": [
                        self._seed("1", "Smoker"),
                        self._seed("2", "Cigarette smoker"),
                    ],
                    "excluded_concept_ids": ["3"],
                },
            }
        )
        assert validate_logic_tree(node) == {"1", "2", "3"}

    def test_rejects_primary_id_not_in_seeds(self) -> None:
        with pytest.raises(Exception):
            LogicNode.model_validate(
                {
                    "kind": "CONCEPT",
                    "criterion": {
                        "snomed_concept_id": "1",
                        "preferred_term": "Smoker",
                        "primary_concept_id": "9999",
                        "seeds": [self._seed("1", "Smoker")],
                    },
                }
            )

    def test_rejects_seed_overlap_with_exclusions(self) -> None:
        """A seed id MUST NOT also appear in excluded_concept_ids."""
        with pytest.raises(Exception):
            LogicNode.model_validate(
                {
                    "kind": "CONCEPT",
                    "criterion": {
                        "snomed_concept_id": "1",
                        "preferred_term": "Smoker",
                        "seeds": [self._seed("1", "Smoker")],
                        "excluded_concept_ids": ["1"],
                    },
                }
            )


# -- apply_rule_edit ----------------------------------------------------------


def _mock_kg_client(run_results: list) -> MagicMock:
    client = MagicMock()
    client.run.side_effect = run_results
    client.close = MagicMock()
    return client


class TestApplyRuleEdit:
    def _updates(self, root: dict | None = None) -> RuleUpdates:
        return RuleUpdates.model_validate(
            {
                "name": "Edited rule",
                "strength": "offer",
                "logic_tree": root or _and_root(),
            }
        )

    def test_writes_new_rule_and_supersedes_predecessor(self) -> None:
        # 1: predecessor lookup, 2: concept verify, 3: insert
        client = _mock_kg_client([
            [{"status": "pending_review", "name": "Old", "strength": "offer",
              "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "Refer..."}],
            [{"concept_id": "49727002", "exists": True}],
            [{"id": "rule:rec-1:edit:abcd1234"}],
        ])
        result = apply_rule_edit(
            client,
            predecessor_rule_id="rule:rec-1:old",
            updates=self._updates(),
            reviewer="qa-lead",
            reason="Tightened criteria",
        )
        assert result["predecessor_id"] == "rule:rec-1:old"
        assert result["rule_id"].startswith("rule:rec-1:old:edit:")
        assert client.run.call_count == 3

    def test_rejects_when_predecessor_missing(self) -> None:
        client = _mock_kg_client([[]])
        with pytest.raises(EditNotApplicable, match="not found"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:missing",
                updates=self._updates(),
                reviewer="qa-lead",
                reason="x",
            )

    def test_rejects_when_predecessor_is_already_superseded(self) -> None:
        client = _mock_kg_client([
            [{"status": "superseded", "name": "Old", "strength": "offer",
              "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "..."}],
        ])
        with pytest.raises(EditNotApplicable, match="status is 'superseded'"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:rec-1:old",
                updates=self._updates(),
                reviewer="qa-lead",
                reason="x",
            )

    def test_rejects_unknown_concept_ids(self) -> None:
        client = _mock_kg_client([
            [{"status": "pending_review", "name": "Old", "strength": "offer",
              "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "..."}],
            [{"concept_id": "49727002", "exists": False}],
        ])
        with pytest.raises(LogicTreeValidationError, match="Unknown SNOMED concept"):
            apply_rule_edit(
                client,
                predecessor_rule_id="rule:rec-1:old",
                updates=self._updates(),
                reviewer="qa-lead",
                reason="x",
            )

    def test_verifier_cypher_targets_canonical_and_legacy_labels(self) -> None:
        # Regression for the parallel-namespace bug where the verifier
        # only looked at (:SnomedConcept {conceptId}) -- which is never
        # written for v2 logic_tree rules. Concepts added via the FE
        # picker live on (:Concept {id}). The verifier MUST accept either
        # so a v2 rule whose concepts only exist on :Concept can be saved.
        from app.services.guidance_rule_edit import _VERIFY_CONCEPTS

        assert ":Concept {id: cid}" in _VERIFY_CONCEPTS, (
            "Verifier must read the canonical (:Concept {id}) node so "
            "concepts surfaced by /terminology/search are recognised."
        )
        assert ":SnomedConcept {conceptId: cid}" in _VERIFY_CONCEPTS, (
            "Verifier must keep the legacy fallback so v1 rules and "
            "older fixtures (only :SnomedConcept) keep working."
        )
        assert (
            "(canonical IS NOT NULL OR legacy IS NOT NULL) AS exists"
            in _VERIFY_CONCEPTS
        ), "Verifier must report exists=true when EITHER label matches."

    def test_accepts_concepts_only_on_canonical_concept_label(self) -> None:
        # End-to-end happy path simulating the live scenario: every
        # picked concept is a canonical (:Concept {id}) node and there
        # is no parallel :SnomedConcept twin. The mocked driver answers
        # the verify round-trip as Neo4j would: a single row per id
        # with exists=true (because the OR over the two OPTIONAL MATCHes
        # resolved). The save MUST succeed.
        client = _mock_kg_client([
            [{"status": "pending_review", "name": "Old", "strength": "offer",
              "compile_scope_id": "NG12", "recommendation_id": "rec-1",
              "verbatim": "Refer..."}],
            [{"concept_id": "49727002", "exists": True}],
            [{"id": "rule:rec-1:edit:abcd1234"}],
        ])
        result = apply_rule_edit(
            client,
            predecessor_rule_id="rule:rec-1:old",
            updates=self._updates(),
            reviewer="qa-lead",
            reason="Picked from terminology search; concept lives on :Concept",
        )
        assert result["rule_id"].startswith("rule:rec-1:old:edit:")


# -- Router integration ------------------------------------------------------


class TestDecisionRouterEditPath:
    def test_returns_new_rule_id_with_predecessor(self, client: TestClient) -> None:
        with patch("app.routers.guidance_rules._kg_client") as mock_factory:
            mock_factory.return_value = _mock_kg_client([
                [{"status": "pending_review", "name": "Old", "strength": "offer",
                  "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "..."}],
                [{"concept_id": "49727002", "exists": True}],
                [{"id": "rule:rec-1:old:edit:abcd1234"}],
            ])
            resp = client.post(
                "/guidance/rules/review/rule:rec-1:old/decision",
                json={
                    "action": "edit",
                    "reviewer": "qa-lead",
                    "reason": "Tightened criteria",
                    "updates": {
                        "name": "Edited rule",
                        "strength": "offer",
                        "logic_tree": _and_root(),
                    },
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "active"
        assert body["predecessor_id"] == "rule:rec-1:old"
        assert body["rule_id"].startswith("rule:rec-1:old:edit:")

    def test_returns_422_on_invalid_logic_tree(self, client: TestClient) -> None:
        with patch("app.routers.guidance_rules._kg_client") as mock_factory:
            mock_factory.return_value = _mock_kg_client([
                [{"status": "pending_review", "name": "Old", "strength": "offer",
                  "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "..."}],
            ])
            resp = client.post(
                "/guidance/rules/review/rule:rec-1:old/decision",
                json={
                    "action": "edit",
                    "reviewer": "qa-lead",
                    "reason": "Empty group",
                    "updates": {
                        "name": "Edited rule",
                        "logic_tree": {"kind": "AND", "children": []},
                    },
                },
            )
        assert resp.status_code == 422

    def test_returns_409_when_predecessor_not_editable(self, client: TestClient) -> None:
        with patch("app.routers.guidance_rules._kg_client") as mock_factory:
            mock_factory.return_value = _mock_kg_client([
                [{"status": "rejected", "name": "Old", "strength": "offer",
                  "compile_scope_id": "NG12", "recommendation_id": "rec-1", "verbatim": "..."}],
            ])
            resp = client.post(
                "/guidance/rules/review/rule:rec-1:old/decision",
                json={
                    "action": "edit",
                    "reviewer": "qa-lead",
                    "reason": "Cannot edit this",
                    "updates": {
                        "name": "Edited rule",
                        "logic_tree": _and_root(),
                    },
                },
            )
        assert resp.status_code == 409

    def test_edit_without_updates_falls_back_to_status_change(self, client: TestClient) -> None:
        with patch("app.routers.guidance_rules._kg_client") as mock_factory:
            mock_factory.return_value = _mock_kg_client([[{"id": "rule:rec-1:old"}]])
            resp = client.post(
                "/guidance/rules/review/rule:rec-1:old/decision",
                json={
                    "action": "edit",
                    "reviewer": "qa-lead",
                    "reason": "Approve with note",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "active"
        assert body["rule_id"] == "rule:rec-1:old"
