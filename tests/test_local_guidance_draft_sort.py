"""TDD: _build_local_draft sorts recommendations naturally within a chapter.

Cypher's ORDER BY chapter_order, stable_key sorts the dotted
recommendation number as a plain string, so rows can legitimately
arrive in "1.11.1" before "1.2.1" order -- _build_local_draft must fix
that with a Python-side natural sort rather than trusting fetch order.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.local_guidance import _build_local_draft


def _row(stable_key: str, rec_title: str) -> dict:
    return {
        "short_code": "RHEUM-01",
        "title": "Rheumatology",
        "publication_date": "2026-01-01",
        "version_label": "v1",
        "chapter_title": "Triage",
        "chapter_order": 0,
        "stable_key": stable_key,
        "rec_title": rec_title,
        "verbatim": f"Verbatim for {rec_title}.",
        "likely_incorrect": False,
    }


def test_build_local_draft_sorts_recommendations_naturally() -> None:
    rows = [_row("1.11.1", "Later"), _row("1.2.1", "Earlier")]

    draft = _build_local_draft(rows, "RHEUM-01")

    stable_keys = [rec.stable_key for rec in draft.chapters[0].recommendations]
    assert stable_keys == ["1.2.1", "1.11.1"]


def test_build_local_draft_preserves_chapter_order() -> None:
    rows = [
        {
            **_row("2.1", "Chapter 2 rec"),
            "chapter_title": "Chapter 2",
            "chapter_order": 1,
        },
        {
            **_row("1.1", "Chapter 1 rec"),
            "chapter_title": "Chapter 1",
            "chapter_order": 0,
        },
    ]

    draft = _build_local_draft(rows, "RHEUM-01")

    assert [ch.title for ch in draft.chapters] == ["Chapter 1", "Chapter 2"]
