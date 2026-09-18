"""Recognise a form tick in every common printed shape.

NHS forms reach us as [X], [x], X, or x. The taught FormSchema owns
which box is which. This module only reads the mark.

Atlas trace:
  DI: DI-5C9CA57B
  DI: DI-50BE367C
  DO: DO-85BBD932
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from libs.pipeline.form_pattern_match import safe_search

if TYPE_CHECKING:
    from libs.pipeline.form_schema_normalizer import FormSchemaItem

_BOX_RE = re.compile(r"\[([^\]]*)\]|\(([^)]*)\)")
_TICK_BOX_RE = re.compile(r"\[([^\]]*)\]")
_BOX_CHECKED_RE = re.compile(r"^(?:[Xx*]|YES|yes)$")
_BARE_TICK_RE = re.compile(r"(?<![A-Za-z0-9])[Xx](?![A-Za-z0-9])")
_YESNO_MARK_RE = re.compile(
    r"\b(Yes|No)\b\s*(?:\[([^\]]*)\]|(?<![A-Za-z0-9])([Xx])(?![A-Za-z0-9]))"
    r"|"
    r"(?:\[([^\]]*)\]|(?<![A-Za-z0-9])([Xx])(?![A-Za-z0-9]))\s*\b(Yes|No)\b",
    re.IGNORECASE,
)


def is_checked_mark(mark: str | None) -> bool:
    """True when box contents or a bare letter are a tick."""
    return bool(_BOX_CHECKED_RE.match((mark or "").strip()))


def mark_in_span(span: str) -> bool | None:
    """Read the first tick or empty box in ``span``.

    Returns True for a tick, False for an empty box, None when the
    span has no mark. A letter X inside a word is not a tick.
    """
    boxes = list(_BOX_RE.finditer(span))
    events: list[tuple[int, bool]] = []
    for match in boxes:
        inner = match.group(1) or match.group(2)
        events.append((match.start(), is_checked_mark(inner)))
    for match in _BARE_TICK_RE.finditer(span):
        if not _inside_box(match.start(), boxes):
            events.append((match.start(), True))
    if not events:
        return None
    events.sort(key=lambda row: row[0])
    return events[0][1]


def item_marks_on_line(
    line: str, items: list[FormSchemaItem]
) -> list[tuple[FormSchemaItem, bool | None]]:
    """Pair each taught item on ``line`` with its tick.

    When the line has one mark per item, pair them left to right. That
    covers ticks after the label, ticks before a score, and a cluster
    of boxes at the end of the row. Otherwise read the first mark after
    each item.
    """
    found = _items_with_spans(line, items)
    if not found:
        return []
    marks = _square_and_bare_marks(line)
    if len(marks) == len(found):
        paired_equal = []
        for (item, _start, _end), (_pos, checked) in zip(found, marks):
            paired_equal.append((item, checked))
        return paired_equal
    paired: list[tuple[FormSchemaItem, bool | None]] = []
    for index, (item, _start, end) in enumerate(found):
        span_end = found[index + 1][1] if index + 1 < len(found) else len(line)
        paired.append((item, mark_in_span(line[end:span_end])))
    return paired


def yes_no_answer(line: str) -> str | None:
    """Return yes, no, or None for a Yes / No row.

    Reads [X], [x], X, and x on either side of the word. A row with
    no single clear answer is None.
    """
    checked: set[str] = set()
    found = False
    for word, mark in _yesno_marks(line):
        found = True
        if is_checked_mark(mark):
            checked.add(word)
    if not found:
        return _two_column_tick_answer(line)
    if len(checked) != 1:
        return None
    return checked.pop()


def _yesno_marks(line: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in _YESNO_MARK_RE.finditer(line):
        if match.group(1):
            word = match.group(1).lower()
            mark = match.group(2) if match.group(2) is not None else match.group(3)
        else:
            word = match.group(6).lower()
            mark = match.group(4) if match.group(4) is not None else match.group(5)
        pairs.append((word, mark or ""))
    return pairs


def _two_column_tick_answer(line: str) -> str | None:
    boxes = [_box_checked(match) for match in _TICK_BOX_RE.finditer(line)]
    if len(boxes) != 2:
        return None
    if boxes[0] and not boxes[1]:
        return "yes"
    if boxes[1] and not boxes[0]:
        return "no"
    return None


def _box_checked(match: re.Match[str]) -> bool:
    return is_checked_mark(match.group(1) or match.group(2))


def _inside_box(index: int, boxes: list[re.Match[str]]) -> bool:
    return any(box.start() <= index < box.end() for box in boxes)


def _square_and_bare_marks(line: str) -> list[tuple[int, bool]]:
    """Return (position, ticked) for square boxes and bare X marks."""
    boxes = list(_TICK_BOX_RE.finditer(line))
    events = [(match.start(), is_checked_mark(match.group(1))) for match in boxes]
    for match in _BARE_TICK_RE.finditer(line):
        if not _inside_box(match.start(), boxes):
            events.append((match.start(), True))
    events.sort(key=lambda row: row[0])
    return events


def _items_with_spans(
    line: str, items: list[FormSchemaItem]
) -> list[tuple[FormSchemaItem, int, int]]:
    found: list[tuple[FormSchemaItem, int, int]] = []
    for item in items:
        match = safe_search(item.pattern, line)
        if match is not None:
            found.append((item, match.start(), match.end()))
    found.sort(key=lambda row: row[1])
    return found
