"""TDD: ignore-this-phrase rules appear on Pipeline Guards.

Atlas: DI-DA60AC55 / DO-7E9AD55B / VT-AEA5D045
"""

from __future__ import annotations

from libs.pipeline.ignore_phrase_catalog import as_ignore_phrase_rows


def test_maps_post_processor_row_to_ignore_phrase() -> None:
    rows = as_ignore_phrase_rows(
        [
            {
                "rule_id": "ppr-1",
                "active": True,
                "action": "suppress",
                "match_text": "nil chest pain",
                "match_label": "finding",
                "notes": "Created from coding review",
            }
        ]
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["family"] == "ignore_phrase"
    assert row["rule_type"] == "suppress"
    assert row["pattern"] == "nil chest pain"
    assert row["source"] == "custom"
    assert row["active"] is True
    assert "coding review" in (row.get("summary") or "")


def test_inactive_ignore_phrase_stays_inactive() -> None:
    rows = as_ignore_phrase_rows(
        [{"rule_id": "ppr-2", "active": False, "action": "suppress", "match_text": "x"}]
    )
    assert rows[0]["active"] is False
