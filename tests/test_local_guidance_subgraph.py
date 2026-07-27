"""TDD: local guideline subgraph returns rules and likely_incorrect."""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.local_guidance import _build_subgraph


def test_build_subgraph_includes_rules_and_totals() -> None:
    """HAS_RULE rows must appear on recommendations with totals.rules."""
    rows = [
        {
            "guideline_id": "SEL-MSK-01",
            "guideline_title": "Local MSK",
            "ingest_version": 1,
            "chapter_id": "ch-1",
            "chapter_title": "Triage",
            "chapter_order": 0,
            "rec_id": "rec-1",
            "stable_key": "rec-1",
            "rec_title": "Same-day",
            "verbatim": "Offer same-day assessment.",
            "likely_incorrect": False,
            "rules": [
                {
                    "rule_id": "rule:abc",
                    "status": "pending_review",
                    "name": "Same-day",
                    "created_at": "2026-07-20",
                }
            ],
        }
    ]

    result = _build_subgraph(rows)

    rec = result["chapters"][0]["recommendations"][0]
    assert rec["rules"][0]["rule_id"] == "rule:abc"
    assert rec["likely_incorrect"] is False
    assert result["totals"]["rules"] == 1


def test_build_subgraph_sorts_recommendations_naturally_within_a_chapter() -> None:
    """Cypher's ORDER BY chapter_order, rec_id does not guarantee dotted-
    number order (rec_id is an internal id, not the visible number) --
    rows are deliberately fed in the "wrong" 1.11.1-before-1.2.1 order
    here to prove the natural-sort pass fixes it regardless of fetch
    order."""
    rows = [
        {
            "guideline_id": "SEL-MSK-01",
            "guideline_title": "Local MSK",
            "ingest_version": 1,
            "chapter_id": "ch-1",
            "chapter_title": "Triage",
            "chapter_order": 0,
            "rec_id": "rec-b",
            "stable_key": "1.11.1",
            "rec_title": "Later",
            "verbatim": "Later recommendation.",
            "likely_incorrect": False,
            "rules": [],
        },
        {
            "guideline_id": "SEL-MSK-01",
            "guideline_title": "Local MSK",
            "ingest_version": 1,
            "chapter_id": "ch-1",
            "chapter_title": "Triage",
            "chapter_order": 0,
            "rec_id": "rec-a",
            "stable_key": "1.2.1",
            "rec_title": "Earlier",
            "verbatim": "Earlier recommendation.",
            "likely_incorrect": False,
            "rules": [],
        },
    ]

    result = _build_subgraph(rows)

    stable_keys = [
        rec["stable_key"] for rec in result["chapters"][0]["recommendations"]
    ]
    assert stable_keys == ["1.2.1", "1.11.1"]


def test_build_subgraph_surfaces_likely_incorrect() -> None:
    """likely_incorrect must be returned for picker messaging."""
    rows = [
        {
            "guideline_id": "SEL-MSK-01",
            "guideline_title": "Local MSK",
            "ingest_version": 1,
            "chapter_id": "ch-1",
            "chapter_title": "Triage",
            "chapter_order": 0,
            "rec_id": "rec-bad",
            "stable_key": "rec-bad",
            "rec_title": "Bad",
            "verbatim": "Unsupported claim.",
            "likely_incorrect": True,
            "rules": [{"rule_id": None}],
        }
    ]

    result = _build_subgraph(rows)
    rec = result["chapters"][0]["recommendations"][0]
    assert rec["likely_incorrect"] is True
    assert rec["rules"] == []
