"""Tests for libs/cypher/coding_decision_queries.py -- CodingDecision audit trail.

Validates Cypher query strings have correct structure and expected parameters.
These are structural tests (no live Neo4j); integration tests with a real
database would use a test container.
"""

from __future__ import annotations

import pytest

from libs.cypher.coding_decision_queries import (
    COUNT_AUDIT_FLAGGED,
    GET_CODING_DECISIONS_FOR_ENCOUNTER,
    GET_CODING_DECISION_STATS,
    UPSERT_CODING_DECISION,
)


class TestUpsertCodingDecision:

    def test_uses_merge_for_idempotency(self):
        assert "MERGE" in UPSERT_CODING_DECISION

    def test_sets_created_at_on_create(self):
        assert "ON CREATE SET d.created_at = datetime()" in UPSERT_CODING_DECISION

    def test_always_sets_updated_at(self):
        assert "d.updated_at        = datetime()" in UPSERT_CODING_DECISION

    def test_contains_required_parameters(self):
        required = [
            "$decision_id",
            "$encounter_id",
            "$patient_id_hash",
            "$entity_text",
            "$entity_label",
            "$assertion",
            "$tier",
            "$decision",
            "$reason",
            "$terminology_score",
            "$consensus_verdict",
            "$model_ids",
        ]
        for param in required:
            assert param in UPSERT_CODING_DECISION, f"Missing {param}"

    def test_returns_decision_id(self):
        assert "RETURN d.decision_id AS decision_id" in UPSERT_CODING_DECISION

    def test_keyed_on_decision_id(self):
        assert "{decision_id: $decision_id}" in UPSERT_CODING_DECISION


class TestGetCodingDecisionsForEncounter:

    def test_matches_by_encounter_id(self):
        assert "{encounter_id: $encounter_id}" in GET_CODING_DECISIONS_FOR_ENCOUNTER

    def test_returns_all_audit_fields(self):
        expected_fields = [
            "decision_id",
            "entity_text",
            "entity_label",
            "assertion",
            "tier",
            "decision",
            "reason",
            "terminology_score",
            "consensus_verdict",
            "model_ids",
            "created_at",
        ]
        for f in expected_fields:
            assert f"AS {f}" in GET_CODING_DECISIONS_FOR_ENCOUNTER, f"Missing {f}"

    def test_ordered_by_created_at(self):
        assert "ORDER BY d.created_at" in GET_CODING_DECISIONS_FOR_ENCOUNTER


class TestGetCodingDecisionStats:

    def test_filters_by_since_datetime(self):
        assert "d.created_at >= datetime($since)" in GET_CODING_DECISION_STATS

    def test_groups_by_tier_decision_reason(self):
        assert "d.tier" in GET_CODING_DECISION_STATS
        assert "d.decision" in GET_CODING_DECISION_STATS
        assert "d.reason" in GET_CODING_DECISION_STATS
        assert "count(d)" in GET_CODING_DECISION_STATS


class TestCountAuditFlagged:

    def test_filters_coded_with_flag(self):
        assert "coded_with_flag" in COUNT_AUDIT_FLAGGED

    def test_filters_by_since(self):
        assert "datetime($since)" in COUNT_AUDIT_FLAGGED

    def test_returns_count(self):
        assert "count(d) AS flagged" in COUNT_AUDIT_FLAGGED
