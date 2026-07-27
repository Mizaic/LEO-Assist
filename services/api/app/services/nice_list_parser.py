"""Recursive HTML list-tree parser for NICE recommendation content.

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")

The NICE Syndication API returns real nested ``<ul>``/``<li>`` XHTML per
recommendation (e.g. NG12 1.2.9's six pathway alternatives, one of which
has its own nested "any of the following" list). Ingestion today
discards this shape entirely: ``_extract_recommendations_from_section``
(``app/routers/nice_guidance.py``) flattens the whole ``<article>`` with
``.get_text(" ", strip=True)`` and only that string is ever stored, as
``verbatim``.

This module parses the SAME ``<article>`` tag's list markup, run
*alongside* (not instead of) that flattening, producing a JSON tree:

    {"lead_text": ..., "items": [{"text": ..., "start": int, "end": int,
     "children": [...]}], "trailing_text": ...}

``start``/``end`` are offsets into the SAME flattened string passed in
as ``flattened_text`` -- computed by locating each item's own text as a
literal substring of it (see ``parse_recommendation_list_structure``'s
docstring for why this is exact, not fuzzy). No guideline text is
re-parsed or re-flattened here; both call sites act on the same
BeautifulSoup ``Tag``.

Consumed downstream by ``pathwayTextSplit.ts``'s ``splitPathways``,
which prefers this structure over its own ", or"-splitting text
heuristic whenever it is present.
"""

from __future__ import annotations

import re
from typing import Any

from bs4.element import Tag

# Mirrors `pathwayTextSplit.ts`'s `TRAILING_CONNECTOR_RE` / `cleanPathwayText`
# -- same rule, ported here. NICE's own markup sometimes nests the trailing
# ", or" / " or" that separates two TOP-LEVEL pathways inside the LAST <li>
# of a nested "any of the following" sub-list instead of the top-level
# item it actually belongs to (confirmed against the NG12 1.2.9 raw HTML
# fixture: item 3's nested list ends with "upper abdominal pain, or",
# where the ", or" is item 4's boundary, not part of the nested list).
# Stripping this from EVERY leaf's own text -- top-level or nested --
# handles both the ordinary case (every top-level item but the last
# carries its own trailing connector) and this misplaced-nesting case
# with one rule, since it only depends on where the text ends, not on
# which list it came from.
_TRAILING_CONNECTOR_RE = re.compile(r",?\s*\bor\b\s*$", re.IGNORECASE)


def _clean_item_text(text: str) -> str:
    """Strip a dangling trailing pathway-boundary connector from one item's
    own text. See the module-level comment on ``_TRAILING_CONNECTOR_RE``.
    """
    return _TRAILING_CONNECTOR_RE.sub("", text).strip()


def _own_text(li: Tag) -> str:
    """Text belonging directly to one ``<li>``, excluding any nested list.

    NICE's markup wraps a nested sub-list in its own ``<p><div
    class="itemizedlist"><ul>...`` sibling paragraph rather than mixing
    it into the item's own text paragraph, so skipping any direct-child
    ``<p>`` that itself contains a ``<ul>`` is sufficient to isolate the
    item's own words.
    """
    parts: list[str] = []
    for p in li.find_all("p", recursive=False):
        if p.find("ul") is not None:
            continue
        text = p.get_text(" ", strip=True)
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _find_nested_ul(li: Tag) -> Tag | None:
    """The nested pathway/AT_LEAST sub-list inside one ``<li>``, if any."""
    return li.find("ul", class_="itemizedlist")


def _parse_items(ul: Tag) -> list[dict[str, Any]]:
    """Parse one ``<ul>``'s direct ``<li>`` children into item dicts.

    Recurses into each item's own nested ``<ul>`` (if any) to populate
    ``children`` -- this is what lets a single-level walk from the
    top-level list capture an arbitrarily (though in practice
    one-level) nested AT_LEAST cluster with no separate code path.
    """
    items: list[dict[str, Any]] = []
    for li in ul.find_all("li", class_="listitem", recursive=False):
        cleaned_text = _clean_item_text(_own_text(li))
        node: dict[str, Any] = {"text": cleaned_text}
        nested_ul = _find_nested_ul(li)
        if nested_ul is not None:
            children = _parse_items(nested_ul)
            if children:
                node["children"] = children
        items.append(node)
    return items


def _surrounding_text(list_tag: Tag, *, before: bool) -> str:
    """Plain-paragraph text immediately before/after ``list_tag`` among its
    own parent's direct children -- the recommendation's lead sentence
    (``before=True``) or any trailing text after the list (rare).
    """
    parent = list_tag.parent
    if parent is None:
        return ""
    parts: list[str] = []
    seen_target = False
    for child in parent.contents:
        if child is list_tag:
            seen_target = True
            continue
        if before and seen_target:
            break
        if not before and not seen_target:
            continue
        if isinstance(child, Tag) and child.name == "p":
            text = child.get_text(" ", strip=True)
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _assign_offsets(node: dict[str, Any], flattened_text: str, cursor: int) -> int:
    """Locate ``node["text"]`` as a literal substring of ``flattened_text``
    starting at ``cursor``, stamping ``start``/``end`` in place and
    returning the new cursor position for the next sibling/child.

    A forward-only ``str.find`` (never re-searching earlier ground) is
    sufficient because both this walk and ``flattened_text`` itself
    (``article.get_text(" ", strip=True)``) visit the document in the
    same left-to-right order -- no fuzzy re-matching is needed between
    the tree and the verbatim string, per this module's own docstring.
    """
    text = node["text"]
    if not text:
        return cursor
    idx = flattened_text.find(text, cursor)
    if idx < 0:
        # Alignment failure (should not happen given the ordering
        # guarantee above): fail closed with a zero-width span rather
        # than guessing a wrong offset, so a consumer can detect
        # start == end and skip highlighting this node instead of
        # highlighting the wrong span.
        node["start"] = cursor
        node["end"] = cursor
        return cursor
    node["start"] = idx
    node["end"] = idx + len(text)
    cursor = node["end"]
    for child in node.get("children", []):
        cursor = _assign_offsets(child, flattened_text, cursor)
    return cursor


def parse_recommendation_list_structure(
    article: Tag,
    flattened_text: str,
) -> dict[str, Any] | None:
    """Parse one recommendation ``<article>``'s own list markup.

    Args:
        article: The already-parsed ``<article class="numbered-paragraph">``
            BeautifulSoup tag (the same one ``_extract_recommendations_from_section``
            already has).
        flattened_text: That SAME article's ``.get_text(" ", strip=True)``
            output -- what is already stored as ``verbatim``. Passed in
            rather than recomputed so caller and parser are guaranteed to
            agree on the exact string being offset against.

    Returns:
        ``None`` when the article has no top-level ``<ul class=
        "itemizedlist">`` at all -- confirmed against a live NICE
        Syndication API probe, most recommendations are a single plain
        sentence (roughly 1 in 5 recommendations across NG238 carry list
        structure) and degrade cleanly to the existing flat-sentence
        wizard path with no structure to report.
    """
    top_ul = article.find("ul", class_="itemizedlist")
    if top_ul is None:
        return None

    items = _parse_items(top_ul)
    if not items:
        return None

    cursor = 0
    for item in items:
        cursor = _assign_offsets(item, flattened_text, cursor)

    structure: dict[str, Any] = {
        "lead_text": _surrounding_text(top_ul, before=True),
        "items": items,
    }
    trailing_text = _surrounding_text(top_ul, before=False)
    if trailing_text:
        structure["trailing_text"] = trailing_text
    return structure
