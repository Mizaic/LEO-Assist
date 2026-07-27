"""TDD: the rule-picker endpoint sorts rule.name naturally, not lexicographically.

Cypher's ORDER BY g.title, ch.title, rule.name sorts the dotted rule
name as a plain string, so "1.11.1" can legitimately come back before
"1.2.1". _sort_picker_rows must fix that with a Python-side natural
sort on the name tiebreak while keeping the coarse guideline/chapter
grouping.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.guidance_rule_picker import _sort_picker_rows


def _row(
    name: str, guideline_title: str = "NG12", chapter_title: str = "Lung cancer"
) -> dict:
    return {
        "rule_id": f"rule:{name}",
        "name": name,
        "guideline_title": guideline_title,
        "chapter_title": chapter_title,
    }


def test_sorts_rule_name_naturally_within_a_chapter() -> None:
    rows = [_row("1.11.1"), _row("1.2.1"), _row("1.2.10"), _row("1.2.2")]

    sorted_rows = _sort_picker_rows(rows)

    assert [row["name"] for row in sorted_rows] == [
        "1.2.1",
        "1.2.2",
        "1.2.10",
        "1.11.1",
    ]


def test_preserves_coarse_guideline_and_chapter_grouping() -> None:
    rows = [
        _row("1.1", guideline_title="NG23"),
        _row("1.1", guideline_title="NG12"),
    ]

    sorted_rows = _sort_picker_rows(rows)

    assert [row["guideline_title"] for row in sorted_rows] == ["NG12", "NG23"]


def test_falls_back_to_rule_id_when_name_is_missing() -> None:
    rows = [{"rule_id": "rule:b", "name": None}, {"rule_id": "rule:a", "name": None}]

    sorted_rows = _sort_picker_rows(rows)  # must not raise

    assert [row["rule_id"] for row in sorted_rows] == ["rule:a", "rule:b"]
