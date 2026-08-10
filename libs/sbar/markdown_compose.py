"""Compose canonical SBAR markdown for widget and export surfaces."""

from __future__ import annotations

import re

_SBAR_STAGES = ("situation", "background", "assessment", "recommendation")
_STAGE_HEADING_RE = re.compile(
    r"^##\s+(situation|background|assessment|recommendation):?\s*\n?",
    re.IGNORECASE | re.MULTILINE,
)


def strip_stage_heading(text: str | None, stage: str) -> str:
    """Remove a leading ## Stage heading from persisted stage markdown."""
    body = (text or "").strip()
    if not body:
        return ""
    pattern = rf"^##\s+{re.escape(stage)}:?\s*\n?"
    return re.sub(pattern, "", body, count=1, flags=re.IGNORECASE).strip()


def content_has_all_sbar_stages(content: str) -> bool:
    """Return True when markdown includes all four canonical stage headings."""
    lower = (content or "").lower()
    for stage in _SBAR_STAGES:
        if not re.search(rf"^##\s+{stage}\s*$", lower, re.MULTILINE):
            return False
    return True


def compose_sbar_markdown(record: dict) -> str:
    """Build widget-ready markdown from an assessment record dict."""
    situation = strip_stage_heading(record.get("situation"), "situation")
    background = strip_stage_heading(record.get("background"), "background")
    assessment = strip_stage_heading(record.get("assessment"), "assessment")
    recommendation = strip_stage_heading(record.get("recommendation"), "recommendation")

    if situation or background or assessment or recommendation:
        return (
            "# SBAR\n\n"
            f"## Situation\n\n{situation or '_Not generated._'}\n\n"
            f"## Background\n\n{background or '_Not generated._'}\n\n"
            f"## Assessment\n\n{assessment or '_Not generated._'}\n\n"
            f"## Recommendation\n\n{recommendation or '_Not generated._'}"
        )

    content = (record.get("content") or "").strip()
    if not content:
        return ""

    normalized = _STAGE_HEADING_RE.sub(
        lambda match: f"## {match.group(1).capitalize()}\n\n",
        content,
    )
    return normalized if content_has_all_sbar_stages(normalized) else content
