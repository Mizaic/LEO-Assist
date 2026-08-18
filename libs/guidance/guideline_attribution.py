"""Guideline author/publisher attribution for SBAR and narrative surfaces.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import re

_NICE_CODE_RE = re.compile(
    r"^(NG|CG|TA|QS|PH|SC|MG|DG|HST|IPG|MTG|CSG|MPG|SSG|COVID)\d+$",
    re.IGNORECASE,
)


def resolve_guideline_author(
    *,
    guideline_id: str = "",
    guideline_author: str | None = None,
    guideline_publisher: str | None = None,
    guideline_source: str | None = None,
) -> str:
    """Return the publishing organisation for a guideline when known."""
    explicit = (guideline_author or guideline_publisher or "").strip()
    if explicit:
        return explicit
    source = (guideline_source or "").strip().lower()
    if source == "nice_syndication_api":
        return "NICE"
    if source == "local_guideline":
        return "Local"
    gid = (guideline_id or "").strip()
    if gid and _NICE_CODE_RE.match(gid):
        return "NICE"
    return ""


def format_guideline_attribution(
    *,
    guideline_id: str = "",
    guideline_title: str = "",
    guideline_author: str | None = None,
    guideline_publisher: str | None = None,
    guideline_source: str | None = None,
) -> str | None:
    """Format a bold Markdown Guideline landmark with author, title, and code."""
    gid = (guideline_id or "").strip()
    gtitle = (guideline_title or "").strip()
    if not gtitle and not gid:
        return None
    author = resolve_guideline_author(
        guideline_id=gid,
        guideline_author=guideline_author,
        guideline_publisher=guideline_publisher,
        guideline_source=guideline_source,
    )
    display_title = gtitle
    if author and gtitle and not gtitle.upper().startswith(f"{author.upper()} "):
        display_title = f"{author} {gtitle}"
    elif author and not gtitle:
        display_title = author
    if display_title and gid and display_title != gid:
        return f"**Guideline:** {display_title} (`{gid}`)"
    return f"**Guideline:** {display_title or gid}"
