"""Generic two-source SBAR conflicts -- no specialty or guideline names."""

from __future__ import annotations

from libs.sbar.prompt_calls import _serialise_recommendation_context
from libs.sbar.source_conflicts import (
    attach_conflicts,
    merge_source_conflicts,
    render_source_conflicts,
)


def test_render_names_both_sides_and_asks_a_person() -> None:
    lines = render_source_conflicts(
        [
            {
                "description": "Form tick says a mass is present. Later note says it settled.",
                "sources": ["form_tick", "later_note"],
            }
        ]
    )
    text = "\n".join(lines)
    assert "### Conflicts (1)" in text
    assert "Form tick says a mass is present" in text
    assert "Later note says it settled" in text
    assert "Please check." in text


def test_attach_conflicts_appends_block() -> None:
    out = attach_conflicts(
        "Primary matches.",
        [{"description": "Tick vs report"}],
    )
    assert out.startswith("Primary matches.")
    assert "### Conflicts (1)" in out
    assert "Tick vs report" in out


def test_render_skips_empty_and_blank_rows() -> None:
    assert render_source_conflicts([]) == []
    assert render_source_conflicts([{"description": "  "}]) == []


def test_merge_keeps_unique_descriptions_in_order() -> None:
    merged = merge_source_conflicts(
        [
            [{"description": "A vs B"}, {"description": "C vs D"}],
            [{"description": "A vs B"}, {"description": "E vs F"}],
        ]
    )
    assert [row["description"] for row in merged] == ["A vs B", "C vs D", "E vs F"]


def test_excluded_present_codes_become_a_conflict() -> None:
    """A match stays visible when the record also has a code that leaf excludes."""
    from libs.sbar.source_conflicts import conflicts_from_excluded_facts

    rows = conflicts_from_excluded_facts(
        [
            {
                "name": "Rule: example",
                "excluded_present": ["65576009"],
            }
        ]
    )
    assert len(rows) == 1
    assert "set aside" in str(rows[0]["description"]).lower()
    assert "65576009" in rows[0]["sources"]


def test_recommendation_context_passes_conflicts_through() -> None:
    blob = _serialise_recommendation_context(
        situation_md="Sit.",
        background_md="Bg.",
        assessment_md="Assess.",
        assessment_rules=[],
        guideline_titles=[],
        guidelines=[],
        conflicts=[{"description": "Tick vs report", "sources": ["form", "report"]}],
    )
    assert "Tick vs report" in blob
    assert "conflicts" in blob
