"""VT-LEO-AI-138 -- Integration-level tests for the evidence-wins merger.

Exercises the ``_merge_duplicate_episodes`` orchestrator with a fake
Neo4j client so the MOVE_LINKS_Q / MARK_MERGED_Q sequence is observable
without requiring a live graph. Covers edge migration ordering,
failure isolation, and idempotency against a stable fetch response.
"""

from __future__ import annotations

from typing import Any

from services.analysis_worker.app.analyzers.episode_builder import _auto_close
from services.analysis_worker.app.analyzers.episode_builder import _cypher


class _FakeClient:
    """Minimal Neo4j client stub that records every ``run`` call."""

    def __init__(self, fetch_rows: list[dict], fail_on: set[str] | None = None):
        self._rows = fetch_rows
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail_on = fail_on or set()

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        if query == _cypher.FETCH_EPISODES_FOR_MERGE_Q:
            return self._rows
        if any(tag in query for tag in self._fail_on):
            raise RuntimeError("simulated failure")
        return []


def _row(
    episode_id: str,
    cancer_type: str,
    referral_date: str | None,
    *,
    texts: list[str] | None = None,
    treatments: int = 0,
    status: str = "completed",
) -> dict:
    return {
        "episode_id": episode_id,
        "cancer_type": cancer_type,
        "referral_date": referral_date,
        "end_date": referral_date,
        "status": status,
        "diagnosis_texts": texts or [],
        "treatment_count": treatments,
        "match_method": "strict_site",
    }


def _move_and_mark_calls(client: _FakeClient) -> list[str]:
    """Return a sequence tagging each call so ordering can be asserted."""
    tags: list[str] = []
    for q, _params in client.calls:
        if q == _cypher.MOVE_LINKS_Q:
            tags.append("move")
        elif q == _cypher.MARK_MERGED_Q:
            tags.append("mark")
        elif q == _cypher.FETCH_EPISODES_FOR_MERGE_Q:
            tags.append("fetch")
    return tags


class TestMergeOrchestrator:
    def test_move_precedes_mark(self):
        """MOVE_LINKS_Q must run before MARK_MERGED_Q per duplicate."""
        rows = [
            _row("a", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _row("b", "unknown", "2024-03-05"),
        ]
        client = _FakeClient(rows)
        _auto_close._merge_duplicate_episodes("p1", client)
        tags = _move_and_mark_calls(client)
        assert tags == ["fetch", "move", "mark"]

    def test_no_merge_when_singleton(self):
        rows = [_row("a", "breast", "2024-03-01", texts=["breast"])]
        client = _FakeClient(rows)
        _auto_close._merge_duplicate_episodes("p1", client)
        assert _move_and_mark_calls(client) == ["fetch"]

    def test_nss_episode_included(self):
        rows = [
            _row("primary", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _row("nss", "non_site_specific", "2024-03-04"),
        ]
        client = _FakeClient(rows)
        _auto_close._merge_duplicate_episodes("p1", client)
        mark_params = [p for q, p in client.calls if q == _cypher.MARK_MERGED_Q]
        assert len(mark_params) == 1
        assert mark_params[0]["dup_id"] == "nss"
        assert mark_params[0]["primary_id"] == "primary"

    def test_move_failure_skips_mark(self):
        """If MOVE_LINKS_Q fails the duplicate is not marked merged --
        preserves the audit trail on that duplicate rather than
        half-merging it."""
        rows = [
            _row("a", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _row("b", "unknown", "2024-03-05"),
        ]
        client = _FakeClient(rows, fail_on={"IS_PART_OF]->(dup"})
        _auto_close._merge_duplicate_episodes("p1", client)
        tags = _move_and_mark_calls(client)
        assert "mark" not in tags
        assert tags[0] == "fetch"
        assert tags.count("move") >= 1

    def test_idempotent_second_pass_no_merge(self):
        """After a successful merge a subsequent rebuild with the dup
        already ``merged`` status must not re-attempt to merge it.
        We simulate by feeding back rows minus the merged dup."""
        rows_first = [
            _row("a", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _row("b", "unknown", "2024-03-05"),
        ]
        client1 = _FakeClient(rows_first)
        _auto_close._merge_duplicate_episodes("p1", client1)
        rows_second = [_row("a", "breast", "2024-03-01", texts=["breast lumpectomy"])]
        client2 = _FakeClient(rows_second)
        _auto_close._merge_duplicate_episodes("p1", client2)
        assert _move_and_mark_calls(client2) == ["fetch"]

    def test_reasoning_persisted(self):
        rows = [
            _row("a", "breast", "2024-03-01", texts=["breast lumpectomy"]),
            _row("b", "unknown", "2024-03-05"),
        ]
        client = _FakeClient(rows)
        _auto_close._merge_duplicate_episodes("p1", client)
        mark = next(p for q, p in client.calls if q == _cypher.MARK_MERGED_Q)
        assert "DI-LEO-AI-137" in mark["reasoning"]
        assert "Primary=a" in mark["reasoning"]
