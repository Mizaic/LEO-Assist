"""Parse NICE companion panels that sit beside numbered recommendations.

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339

NG12 1.7.1 stores the weighted 7-point checklist in a sibling
``div.panel.panel--primary`` after the recommendation ``<article>``,
not inside it. ``parse_recommendation_list_structure`` never sees that
panel; this module attaches it as ``CompanionPanels`` on the
recommendation dict so the highlight wizard can expand score thresholds
into weighted OR-of-groups logic.
"""

from __future__ import annotations

import re
from typing import Any

from bs4.element import NavigableString, Tag

_SCORE_THRESHOLD_RE = re.compile(
    r"\bscore\s+of\s+(\d+)\s+or\s+more\b",
    re.IGNORECASE,
)
_POINTS_EACH_RE = re.compile(
    r"scoring\s+(\d+)\s+points?\s+each",
    re.IGNORECASE,
)
_WEIGHTED_TITLE_RE = re.compile(r"\bweighted\b.*\bchecklist\b", re.IGNORECASE)


def parse_score_threshold(text: str | None) -> int | None:
    """Return N from 'score of N or more', or None when absent."""
    if not text:
        return None
    match = _SCORE_THRESHOLD_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def _panel_title(panel: Tag) -> str:
    heading = panel.find(["h5", "h4", "h3", "h6"])
    if heading is not None:
        return heading.get_text(" ", strip=True)
    title_attr = panel.get("title")
    if isinstance(title_attr, str) and title_attr.strip():
        return title_attr.strip()
    return ""


def _list_items(ul: Tag) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for li in ul.find_all("li", recursive=False):
        text = li.get_text(" ", strip=True)
        if text:
            items.append({"text": text.rstrip(".")})
    if items:
        return items
    for li in ul.find_all("li"):
        text = li.get_text(" ", strip=True)
        if text:
            items.append({"text": text.rstrip(".")})
    return items


def _group_from_paragraph(p: Tag) -> dict[str, Any] | None:
    label = p.get_text(" ", strip=True)
    if not label:
        return None
    points_match = _POINTS_EACH_RE.search(label)
    points = int(points_match.group(1)) if points_match else 1
    sibling = p.find_next_sibling()
    while sibling is not None and isinstance(sibling, NavigableString):
        sibling = sibling.next_sibling
    if not isinstance(sibling, Tag):
        return None
    ul = sibling if sibling.name == "ul" else sibling.find("ul")
    if ul is None:
        return None
    items = _list_items(ul)
    if not items:
        return None
    return {"label": label, "points": points, "items": items}


def parse_companion_panel(
    panel: Tag,
    recommendation_text: str | None = None,
) -> dict[str, Any] | None:
    """Parse one ``div.panel`` into a companion dict, or None if empty."""
    title = _panel_title(panel)
    groups: list[dict[str, Any]] = []
    for p in panel.find_all("p"):
        group = _group_from_paragraph(p)
        if group is not None:
            groups.append(group)
    if not groups and not title:
        return None

    kind = (
        "weighted_checklist" if _WEIGHTED_TITLE_RE.search(title) else "panel"
    )
    threshold = parse_score_threshold(recommendation_text)
    payload: dict[str, Any] = {
        "title": title,
        "kind": kind,
        "groups": groups,
    }
    if threshold is not None:
        payload["threshold"] = threshold
    return payload


def _next_element_sibling(tag: Tag) -> Tag | None:
    sibling = tag.next_sibling
    while sibling is not None:
        if isinstance(sibling, Tag):
            return sibling
        sibling = sibling.next_sibling
    return None


def parse_companion_panels_after_article(
    article: Tag,
    recommendation_text: str | None = None,
) -> list[dict[str, Any]]:
    """Return companion panels immediately following ``article``.

    Stops before the next numbered recommendation article so a panel
    belongs only to the preceding recommendation (NG12 1.7.1 shape).
    """
    panels: list[dict[str, Any]] = []
    sibling = _next_element_sibling(article)
    while sibling is not None:
        classes = sibling.get("class") or []
        if sibling.name == "article" and "numbered-paragraph" in classes:
            break
        if sibling.name == "div" and "panel" in classes:
            parsed = parse_companion_panel(sibling, recommendation_text)
            if parsed is not None:
                panels.append(parsed)
            sibling = _next_element_sibling(sibling)
            continue
        # Skip whitespace wrappers; stop on other substantive blocks.
        if sibling.name in {"div", "section"} and not (
            sibling.get_text(strip=True) == ""
        ):
            break
        sibling = _next_element_sibling(sibling)
    return panels
