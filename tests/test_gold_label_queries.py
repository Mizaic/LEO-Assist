from __future__ import annotations

from libs.cypher import gold_label_queries as q


def test_gold_label_query_contains_required_fields() -> None:
    assert "label_id" in q.UPSERT_GOLD_LABEL
    assert "entities_json" in q.UPSERT_GOLD_LABEL
    assert "quality_score" in q.UPSERT_GOLD_LABEL


def test_gold_label_indexes_present() -> None:
    assert any("gold_label_id" in s for s in q.CREATE_GOLD_LABEL_INDEXES)

