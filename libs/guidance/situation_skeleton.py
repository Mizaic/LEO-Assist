"""Build situation shells from NICE list structure / prose heuristics.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Mirrors the Highlight Wizard's ``splitPathways`` contract in
``pathwayTextSplit.ts`` so AI generation and HITL reopen agree on
situation arity and source.
"""

from __future__ import annotations

import json
import re
from typing import Any

from libs.guidance.situation_draft import SituationShell

_TOP_LEVEL_OR_RE = re.compile(r",\s*or\b\s*", re.IGNORECASE)
_AT_LEAST_MARKER_RE = re.compile(
    r"\b(?:\d+|one|two|three|any)\s+or\s+more\s+of\s+the\s+following\b"
    r"|\bany\s+of\s+the\s+following\b",
    re.IGNORECASE,
)
_TABLE_MARKER_RE = re.compile(
    r"\bthresholds?\s+in\s+table\b|\baccording\s+to\s+(?:the\s+)?table\b",
    re.IGNORECASE,
)


def parse_list_structure(raw: Any) -> dict[str, Any] | None:
    """Normalise listStructureJson from Neo4j (str or dict) to a dict."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def looks_like_table_thresholds(text: str | None) -> bool:
    """True when the recommendation points at an external threshold table."""
    return bool(text and _TABLE_MARKER_RE.search(text))


def _structure_items_align_with_text(text: str, items: list[dict[str, Any]]) -> bool:
    """True when every item span is a real substring of `text`."""
    for item in items:
        item_text = str(item.get("text") or "")
        start = int(item.get("start") or 0)
        end = int(item.get("end") or 0)
        if not item_text or end > len(text) or start >= end:
            return False
        if text[start:end] != item_text:
            return False
    return True


def _connector_reads_as_or(text: str, prev_end: int, next_start: int) -> bool:
    gap = text[prev_end:next_start]
    if re.search(r"\bor\b", gap, re.IGNORECASE):
        return True
    if re.search(r"\band\b", gap, re.IGNORECASE):
        return False
    return True


def split_by_or_heuristic(text: str | None) -> list[SituationShell] | None:
    """Comma-before-or split; None when fewer than two meaningful segments."""
    if not text or not text.strip():
        return None
    split_points = [m.end() for m in _TOP_LEVEL_OR_RE.finditer(text)]
    if not split_points:
        return None
    boundaries: list[SituationShell] = []
    cursor = 0
    for point in split_points:
        boundaries.append(
            SituationShell(
                text=text[cursor:point],
                start=cursor,
                end=point,
                source="heuristic",
            )
        )
        cursor = point
    boundaries.append(
        SituationShell(
            text=text[cursor:],
            start=cursor,
            end=len(text),
            source="heuristic",
        )
    )
    meaningful = [b for b in boundaries if re.search(r"[A-Za-z]", b.text)]
    return meaningful if len(meaningful) >= 2 else None


def _structure_items_share_heuristic_segment(
    text: str, items: list[dict[str, Any]]
) -> bool:
    heuristic = split_by_or_heuristic(text)
    if not heuristic or len(heuristic) == len(items):
        return False
    touched: set[int] = set()
    for item in items:
        start = int(item.get("start") or 0)
        idx = next(
            (i for i, b in enumerate(heuristic) if b.start <= start < b.end),
            -1,
        )
        touched.add(idx)
    return len(touched) < len(items)


def split_from_structure(
    text: str | None, structure: dict[str, Any] | None
) -> list[SituationShell] | None | str:
    """Return shells, None (fall through), or 'not_a_split' (and-joined list)."""
    if not structure or not isinstance(structure.get("items"), list):
        return None
    items = structure["items"]
    if len(items) < 2:
        return None
    if text and not _structure_items_align_with_text(text, items):
        return None
    lead = str(structure.get("lead_text") or "")
    if _AT_LEAST_MARKER_RE.search(lead):
        return None
    if text:
        for i in range(len(items) - 1):
            prev_end = int(items[i].get("end") or 0)
            next_start = int(items[i + 1].get("start") or 0)
            if not _connector_reads_as_or(text, prev_end, next_start):
                return "not_a_split"
        if _structure_items_share_heuristic_segment(text, items):
            return None
    shells: list[SituationShell] = []
    for item in items:
        children = item.get("children")
        shells.append(
            SituationShell(
                text=str(item.get("text") or ""),
                start=int(item.get("start") or 0),
                end=int(item.get("end") or 0),
                source="structure",
                structure_children=children if isinstance(children, list) else None,
            )
        )
    return shells


def build_situation_skeleton(
    text: str | None,
    structure: dict[str, Any] | None = None,
    *,
    threshold_rows: list[str] | list[dict[str, Any]] | None = None,
) -> list[SituationShell]:
    """Preferred entry: structure (or-joined) > heuristic > single/tree shell.

    Table-threshold prose without structure does NOT invent multiple prose
    situations. If ``threshold_rows`` are supplied, emit one ``source=\"tree\"``
    shell per row; otherwise one shell with ``source=\"tree\"`` (HITL table
    entry) or ``source=\"single\"``.
    """
    parsed = (
        parse_list_structure(structure)
        if not isinstance(structure, dict)
        else structure
    )
    structural = split_from_structure(text, parsed)
    if structural == "not_a_split":
        return [
            SituationShell(
                text=(text or "").strip(),
                start=0,
                end=len(text or ""),
                source="single",
            )
        ]
    if isinstance(structural, list):
        return structural

    if looks_like_table_thresholds(text):
        if threshold_rows:
            from libs.guidance.situation_draft import tree_shells_from_threshold_rows

            rows = tree_shells_from_threshold_rows(threshold_rows)
            if rows:
                return rows
        body = (text or "").strip()
        return [
            SituationShell(
                text=body,
                start=0,
                end=len(body),
                source="tree",
            )
        ]

    heuristic = split_by_or_heuristic(text)
    if heuristic:
        # NG12 1.1.2: structure fell through as a shared quantifier list
        # -- attach those items onto every heuristic situation so both
        # "2 or more" and "1 or more" shells carry the same symptoms.
        shared_items = _shared_quantifier_structure_items(text, parsed)
        if shared_items:
            return [
                shell.model_copy(update={"structure_children": shared_items})
                for shell in heuristic
            ]
        return heuristic
    body = (text or "").strip()
    return [
        SituationShell(
            text=body,
            start=0,
            end=len(body),
            source="single",
        )
    ]


def _shared_quantifier_structure_items(
    text: str | None, structure: dict[str, Any] | None
) -> list[dict[str, Any]] | None:
    """Return structure items when they are a shared AT_LEAST list, else None."""
    if not structure or not isinstance(structure.get("items"), list):
        return None
    items = structure["items"]
    if len(items) < 2:
        return None
    lead = str(structure.get("lead_text") or "")
    if _AT_LEAST_MARKER_RE.search(lead):
        return [dict(i) for i in items if isinstance(i, dict)]
    if text and _structure_items_share_heuristic_segment(text, items):
        return [dict(i) for i in items if isinstance(i, dict)]
    return None


def skeleton_for_prompt(shells: list[SituationShell]) -> list[dict[str, Any]]:
    """Compact JSON for the extraction prompt (no conditions yet)."""
    out: list[dict[str, Any]] = []
    for i, shell in enumerate(shells):
        out.append(
            {
                "index": i,
                "letter": chr(ord("A") + i) if i < 26 else str(i),
                "text": shell.text,
                "start": shell.start,
                "end": shell.end,
                "source": shell.source,
            }
        )
    return out
