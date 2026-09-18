"""Does a row of a taught blood-results table actually report a result?

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996

A taught referral form prints its blood-results table whether or not the
tests were resulted, so a battery label on a row is evidence of nothing.
A row reports a result only when it shows a value, a unit-bearing value,
or a specimen date in a cell of its own.

Value detection reuses the ``name value unit`` patterns from
:mod:`libs.pipeline.blood_panel_table`, which has always required a value
before it emits an observable.
"""

from __future__ import annotations

import re

from libs.pipeline.blood_panel_table import (
    UNIT_PATTERN,
    VALUE_PATTERN,
    has_value_unit_pair,
)
from libs.pipeline.observation_date import DATE_TOKEN

# A cell holding nothing but a result, e.g. "124 g/L", "12.5", "<0.5".
_VALUE_CELL_RE = re.compile(rf"{VALUE_PATTERN}(?:\s*{UNIT_PATTERN})?", re.IGNORECASE)

# A cell holding nothing but a specimen date: 23.06.26, 23/06/2026,
# 2026-06-23, or 23 Jun 2026.
_DATE_CELL_RE = re.compile(DATE_TOKEN)

# A result carrying its own unit, e.g. "6 ku/L". Required of a part of a
# shared cell, where a bare number is too weak to read as a result.
_VALUE_WITH_UNIT_RE = re.compile(rf"{VALUE_PATTERN}\s*{UNIT_PATTERN}", re.IGNORECASE)


def _cells(row: str) -> list[str]:
    """Return the trimmed cells of a markdown table row."""
    if "|" not in row:
        return [row.strip()]
    return [cell.strip() for cell in row.split("|")]


def _shared_cell_parts(cell: str) -> list[str]:
    """Split a cell that holds more than one field, e.g. a date and a result.

    Tumour-marker rows on the Sherwood gynaecology form are written
    ``| CA 125 | 02 Jun 2026, 6 ku/L | 2ww Gynae |``. Returns an empty
    list for an ordinary single-field cell, so those keep reading
    exactly as before.
    """
    parts = [part.strip() for part in cell.split(",") if part.strip()]
    return parts if len(parts) > 1 else []


def row_has_specimen_date(row: str) -> bool:
    """Return True when a cell of *row*, or a field of one, is a date.

    The date must fill its cell, or its own comma-separated field of a
    shared cell. A date inside prose, such as the "BLOODS DONE TODAY
    23.6.26" boilerplate, says nothing about which battery on which row
    was resulted.
    """
    for cell in _cells(row):
        if cell and _DATE_CELL_RE.fullmatch(cell):
            return True
        if any(_DATE_CELL_RE.fullmatch(part) for part in _shared_cell_parts(cell)):
            return True
    return False


def row_has_value_cell(row: str) -> bool:
    """Return True when a cell of *row*, or a field of one, is a result.

    A shared cell must carry the unit as well, because a bare number
    beside free text is as likely to be a count or a grade as a result.
    """
    for cell in _cells(row):
        if cell and _VALUE_CELL_RE.fullmatch(cell):
            return True
        if any(
            _VALUE_WITH_UNIT_RE.fullmatch(part) for part in _shared_cell_parts(cell)
        ):
            return True
    return False


def label_has_value(text: str, label: str) -> bool:
    """Return True when *label* is followed by a numeric value in *text*.

    The value must sit directly after the label, so "Hb 118 g/L" counts
    and a bare "Hb" in a list of analyte names does not.
    """
    clean = (label or "").strip()
    if not clean:
        return False
    pattern = (
        rf"(?<![A-Za-z0-9]){re.escape(clean)}(?![A-Za-z0-9])"
        rf"\s*[:=]?\s*{VALUE_PATTERN}(?:\s*{UNIT_PATTERN})?"
    )
    try:
        return re.search(pattern, text, re.IGNORECASE) is not None
    except re.error:
        return False


def row_reports_a_result(row: str, analyte_labels: list[str]) -> bool:
    """Return True when *row* shows that a result was reported.

    Args:
        row: One line of the letter, usually a markdown table row.
        analyte_labels: The taught analyte labels for the battery matched
            on this row.
    """
    if row_has_specimen_date(row) or row_has_value_cell(row):
        return True
    if has_value_unit_pair(row):
        return True
    return any(label_has_value(row, label) for label in analyte_labels)
