from __future__ import annotations

from libs.cypher import training_candidate_queries as q


def test_candidate_query_contains_required_fields() -> None:
    assert "candidate_id" in q.UPSERT_TRAINING_CANDIDATE
    assert "text" in q.UPSERT_TRAINING_CANDIDATE
    assert "status" in q.UPSERT_TRAINING_CANDIDATE


def test_candidate_indexes_present() -> None:
    assert any(
        "training_candidate_id" in s for s in q.CREATE_TRAINING_CANDIDATE_INDEXES
    )
    assert any(
        "training_candidate_status" in s for s in q.CREATE_TRAINING_CANDIDATE_INDEXES
    )
