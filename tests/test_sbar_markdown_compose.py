"""Tests for canonical SBAR markdown composition."""

from libs.sbar.markdown_compose import (
    compose_sbar_markdown,
    content_has_all_sbar_stages,
    strip_stage_heading,
)


def test_content_has_all_sbar_stages_requires_four_headings() -> None:
    full = (
        "## Situation\n\nS\n\n## Background\n\nB\n\n"
        "## Assessment\n\nA\n\n## Recommendation\n\nR"
    )
    assert content_has_all_sbar_stages(full) is True
    partial = "## Assessment\n\nA\n\n## Recommendation\n\nR"
    assert content_has_all_sbar_stages(partial) is False
    colon_situation = (
        "## Situation:\n\nS\n\n## Background\n\nB\n\n"
        "## Assessment\n\nA\n\n## Recommendation\n\nR"
    )
    assert content_has_all_sbar_stages(colon_situation) is False


def test_strip_stage_heading_removes_colon_heading() -> None:
    raw = "## Situation:\nWe have received a referral."
    assert strip_stage_heading(raw, "situation") == "We have received a referral."


def test_compose_prefers_stage_fields_over_content() -> None:
    content = (
        "## Situation\n\nFrom content.\n\n## Background\n\nBg.\n\n"
        "## Assessment\n\nA.\n\n## Recommendation\n\nR."
    )
    md = compose_sbar_markdown(
        {
            "content": content,
            "situation": "## Situation:\nFrom field.",
            "background": "Recent Symptoms:\n- cough",
            "assessment": "A field.",
            "recommendation": "R field.",
        }
    )
    assert "From field." in md
    assert "Recent Symptoms:" in md
    assert "From content." not in md


def test_compose_rebuilds_from_fields_when_content_incomplete() -> None:
    md = compose_sbar_markdown(
        {
            "content": "## Assessment\n\nA only.\n\n## Recommendation\n\nR only.",
            "situation": "## Situation:\nUnilateral nipple discharge.",
            "background": "Recent symptoms listed.",
            "assessment": "Urgent 2WW referral.",
            "recommendation": "Refer via 2WW.",
        }
    )
    assert "## Situation" in md
    assert "Unilateral nipple discharge." in md
    assert "## Background" in md
    assert "Recent symptoms listed." in md
    assert "## Assessment" in md
    assert "## Recommendation" in md
