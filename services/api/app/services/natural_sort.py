"""Numeric-segment ("natural") sort key for dotted NICE section numbers.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Cypher's default string ``ORDER BY`` cannot compare a dotted id like
``"1.11.1"`` numerically -- it sorts ``"1.11.1"`` before ``"1.2.1"``
because the character ``"1"`` sorts before ``"2"``. This mirrors
``naturalSortCompare`` in
``services/ui/src/app/admin/guidance/naturalSort.ts`` so the frontend
and backend agree on the same ordering: split on digit runs, compare
numeric segments as integers, everything else as plain strings.
"""

from __future__ import annotations

import re

_DIGIT_RUN_RE = re.compile(r"(\d+)")


def natural_sort_key(value: str | None) -> tuple[object, ...]:
    """Sort key that orders dotted ids numerically, segment by segment.

    ``"1.2.1"`` -> ``(1, ".", 2, ".", 1)``; ``"1.11.1"`` -> ``(1, ".", 11, ".", 1)``.
    Comparing these tuples element-wise puts ``"1.2.1"`` before
    ``"1.11.1"`` and ``"1.9"`` before ``"1.10"``, unlike plain string
    comparison. Non-numeric segments stay strings, and each numeric
    segment is prefixed with ``0`` (a stable, invisible int/str type
    tag) so a numeric segment and a non-numeric one at the same tuple
    position never raise ``TypeError`` when compared -- Python cannot
    order ``int`` against ``str`` directly.
    """
    if not value:
        return ((1, ""),)
    segments = [seg for seg in _DIGIT_RUN_RE.split(value) if seg]
    return tuple((0, int(seg)) if seg.isdigit() else (1, seg) for seg in segments)
