"""Seed procedure and analyte entities from taught ordered_tests batteries.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996

Seeding only happens where the letter reports a result. A taught form
prints its blood-results table on every referral, so a battery label on
its own proves nothing: it cannot support a "present" claim that the test
was done, nor an "absent" claim that it was not. See
:mod:`libs.pipeline.lab_result_evidence` for what counts as a result.
"""

from __future__ import annotations

import re
from typing import Any

from libs.pipeline.form_pattern_match import safe_search
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
)
from libs.pipeline.lab_result_evidence import label_reading, row_reports_a_result

TAUGHT_TEST_ROW_SOURCE = "form_schema_ordered_tests"


def is_taught_test_row(entity: dict[str, Any]) -> bool:
    """Return True for a test-row fact seeded from a taught FormSchema."""
    return str(entity.get("__source") or "") == TAUGHT_TEST_ROW_SOURCE


def carries_taught_test_row_code(entity: dict[str, Any]) -> bool:
    """Return True when a test-row fact still holds the code it was taught.

    A row taught without a code is looked up like any fact, so its code is
    a guess and gets checked like one.
    """
    if not is_taught_test_row(entity):
        return False
    taught = str(entity.get("snomed_code") or "").strip()
    return bool(taught) and str(entity.get("concept_id") or "").strip() == taught


def row_matches_battery(row: str, item: FormSchemaItem) -> bool:
    """Return True when *row* carries this battery's taught label."""
    if not item.pattern:
        return False
    return safe_search(item.pattern, row) is not None


def battery_row_reports_a_result(row: str, item: FormSchemaItem) -> bool:
    """Return True when *row* is this battery's row and reports a result.

    Completeness uses this too, so a row counts as filled in exactly when
    it becomes a fact.
    """
    return row_matches_battery(row, item) and row_reports_a_result(
        row, _analyte_labels(item)
    )


def _find_label_span(text: str, label: str) -> tuple[int, int]:
    """Return start/end char offsets for *label* in *text*, or (0, len)."""
    if not label:
        return 0, 0
    try:
        match = re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE)
    except re.error:
        match = None
    if match is None:
        idx = text.lower().find(label.lower())
        if idx < 0:
            return 0, len(label)
        return idx, idx + len(label)
    return match.start(), match.end()


def _analyte_labels(item: FormSchemaItem) -> list[str]:
    return [str(a.get("label") or "") for a in item.analytes]


def _resulted_rows(text: str, item: FormSchemaItem) -> list[str]:
    """Return this battery's rows that report a result."""
    return [row for row in text.splitlines() if battery_row_reports_a_result(row, item)]


def _seed_battery_entity(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    item: FormSchemaItem,
) -> None:
    label = (item.pattern or item.entity_text or "").strip()
    if not label:
        return
    key = f"procedure:{label.casefold()}"
    if key in seen:
        return
    seen.add(key)
    start, end = _find_label_span(text, label)
    entities.append(
        {
            "text": label,
            "label": label,
            "entity_text": item.entity_text or item.procedure_display or label,
            "snomed_code": item.procedure_snomed or "",
            "concept_id": item.procedure_snomed or None,
            "start": start,
            "end": end,
            "assertion": item.assertion or "present",
            "semantic_tag": item.semantic_tag or "procedure",
            "__source": TAUGHT_TEST_ROW_SOURCE,
        }
    )


def _analyte_entity(
    seen: set[str],
    text: str,
    analyte: dict[str, str],
    item: FormSchemaItem,
) -> dict[str, Any] | None:
    label = str(analyte.get("label") or "").strip()
    code = str(analyte.get("snomed_code") or "").strip()
    if not label:
        return None
    # A single-result row (FIT) gives the row and its analyte one label.
    key = f"observable:{label.casefold()}"
    if key in seen:
        return None
    seen.add(key)
    start, end = _find_label_span(text, label)
    return {
        "text": label,
        "label": label,
        "snomed_code": code,
        "concept_id": code or None,
        "start": start,
        "end": end,
        "assertion": item.assertion or "present",
        "semantic_tag": "observable entity",
        "__source": TAUGHT_TEST_ROW_SOURCE,
    }


def _first_reading(rows: list[str], label: str) -> tuple[str, str] | None:
    for row in rows:
        reading = label_reading(row, label)
        if reading is not None:
            return reading
    return None


def _seed_item(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    item: FormSchemaItem,
) -> None:
    """Seed one battery and its resulted analytes, or nothing at all."""
    rows = _resulted_rows(text, item)
    if not rows:
        return
    _seed_battery_entity(entities, seen, text, item)
    for analyte in item.analytes:
        reading = _first_reading(rows, str(analyte.get("label") or ""))
        if reading is None:
            continue
        entity = _analyte_entity(seen, text, analyte, item)
        if entity is None:
            continue
        value, unit = reading
        entity["value"] = value
        entity["unit"] = unit or None
        entities.append(entity)


def seed_ordered_tests_entities(
    encounter_text: str,
    schema: FormSchema,
) -> list[dict[str, Any]]:
    """Seed procedure and analyte entities from taught ordered_tests batteries.

    Args:
        encounter_text: The letter text, normalised or raw.
        schema: The taught FormSchema for this form.

    Returns:
        One entity per battery that reports a result, plus one per analyte
        that carries its own value. An empty list when the taught table is
        printed but unresulted.
    """
    if not encounter_text.strip() or not schema.sections:
        return []
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in schema.sections:
        if section.section_type != "ordered_tests":
            continue
        for item in section.items:
            _seed_item(entities, seen, encounter_text, item)
    return entities


__all__ = [
    "TAUGHT_TEST_ROW_SOURCE",
    "battery_row_reports_a_result",
    "carries_taught_test_row_code",
    "is_taught_test_row",
    "row_matches_battery",
    "seed_ordered_tests_entities",
]
