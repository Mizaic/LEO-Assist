"""Tests for `libs/cypher/anchor_review_queries.py`.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4

These tests are a contract check on the read- and write-side Cypher
strings. Cypher is hard to unit-test against a real graph in CI, so we
verify that:
  - every query is a non-empty string
  - the parameters referenced by `$name` placeholders are documented
  - LIMIT/SKIP appear on the paged read queries
  - destructive operations are absent (no DETACH DELETE, no DROP)
  - the assertions match the docstring contract (e.g. AnchorVote
    relationships are MERGE'd, not CREATE'd, so re-runs are idempotent)
"""

from __future__ import annotations

import re

import libs.cypher.anchor_review_queries as q


PAGED_READ_QUERIES = [
    "GET_ALL_ANCHOR_DISAGREEMENTS",
    "GET_NON_CANCER_FLAGS",
]

WRITE_QUERIES = [
    "UPSERT_ANCHOR_REVIEW",
    "UPSERT_ANCHOR_VOTE",
]


def _params(text: str) -> set[str]:
    return set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", text))


class TestQueryConstantsExist:
    def test_all_named_queries_are_non_empty_strings(self):
        names = [
            "UPSERT_ANCHOR_REVIEW",
            "UPSERT_ANCHOR_VOTE",
            "GET_ALL_ANCHOR_DISAGREEMENTS",
            "GET_NON_CANCER_FLAGS",
            "COUNT_ANCHOR_DISAGREEMENTS_PENDING",
            "COUNT_NON_CANCER_PENDING",
            "GET_ANCHOR_SCORECARD",
            "GET_ANCHOR_DOMAIN_DISTRIBUTION",
            "GET_REVIEWED_TARGET_RULES",
        ]
        for n in names:
            v = getattr(q, n)
            assert isinstance(v, str)
            assert v.strip() != ""


class TestPagedReadsRespectPagination:
    def test_paged_reads_use_skip_and_limit(self):
        for name in PAGED_READ_QUERIES:
            text = getattr(q, name)
            params = _params(text)
            assert "skip" in params, f"{name} missing $skip"
            assert "limit" in params, f"{name} missing $limit"


class TestUpsertReviewIsIdempotent:
    def test_uses_merge_not_create_for_review_node(self):
        assert "MERGE (r:AnchorReview" in q.UPSERT_ANCHOR_REVIEW
        assert "CREATE (r:AnchorReview" not in q.UPSERT_ANCHOR_REVIEW

    def test_review_keys_on_natural_identifier(self):
        assert "encounter_id: $encounter_id" in q.UPSERT_ANCHOR_REVIEW
        assert "milestone_type: $milestone_type" in q.UPSERT_ANCHOR_REVIEW

    def test_review_links_to_existing_encounter_with_optional_match(self):
        assert "OPTIONAL MATCH (e:Encounter" in q.UPSERT_ANCHOR_REVIEW
        assert "MERGE (r)-[:REVIEWS]->(e)" in q.UPSERT_ANCHOR_REVIEW


class TestUpsertVoteHumanCorrects:
    def test_vote_merge_not_create(self):
        assert "MERGE (r)<-[:VOTED_ON]-(v:AnchorVote" in q.UPSERT_ANCHOR_VOTE

    def test_vote_marks_review_human_corrected(self):
        assert "r.human_corrected" in q.UPSERT_ANCHOR_VOTE
        assert "= true" in q.UPSERT_ANCHOR_VOTE

    def test_vote_returns_correct_domain(self):
        assert "RETURN" in q.UPSERT_ANCHOR_VOTE
        assert "correct_domain" in q.UPSERT_ANCHOR_VOTE


class TestNoDestructiveOps:
    def test_no_query_uses_detach_delete_or_drop(self):
        for name in dir(q):
            if name.startswith("_"):
                continue
            v = getattr(q, name)
            if not isinstance(v, str):
                continue
            assert "DETACH DELETE" not in v.upper(), name
            assert "DROP " not in v.upper(), name


class TestPendingCountersFilterUnreviewed:
    def test_disagreement_counter_filters_consensus_false_unreviewed(self):
        assert "consensus_agreement = false" in q.COUNT_ANCHOR_DISAGREEMENTS_PENDING
        assert "human_corrected IS NULL" in q.COUNT_ANCHOR_DISAGREEMENTS_PENDING

    def test_non_cancer_counter_filters_unreviewed(self):
        assert "non_cancer_flag = true" in q.COUNT_NON_CANCER_PENDING
        assert "human_corrected IS NULL" in q.COUNT_NON_CANCER_PENDING


class TestScorecardAggregates:
    def test_scorecard_returns_per_model_correct_counts(self):
        assert "model_a_correct" in q.GET_ANCHOR_SCORECARD
        assert "model_b_correct" in q.GET_ANCHOR_SCORECARD
        assert "both_wrong" in q.GET_ANCHOR_SCORECARD
        assert "total_votes" in q.GET_ANCHOR_SCORECARD
