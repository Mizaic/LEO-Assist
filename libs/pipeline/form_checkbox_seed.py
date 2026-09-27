"""Seed ticked-checkbox facts at raw-letter offsets.

Atlas trace:
  DI: DI-0B907354
  DO: DO-AC2014F7
  VT: VT-24D1E4F6
  Risk: R-3926E48D

The normaliser seals checkbox rows so the model cannot re-quote a
synthesised sentence. This module places the ticked fact on the words
that actually appear in the letter.
"""

from __future__ import annotations

import re
from typing import Any

from libs.completeness.schema import concept_ids_for_item_pattern
from libs.pipeline.form_pattern_match import safe_search
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    _find_matching_section,
    _yes_no_answer,
)
from libs.pipeline.form_tick_marks import item_marks_on_line

_CHECKBOX_TYPES = frozenset(
    {"checkbox_single", "checkbox_multi", "checkbox_yesno", "scale"}
)


TAUGHT_CHECKBOX_SOURCE = "form_schema_checkbox"


def is_taught_checkbox(entity: dict[str, Any]) -> bool:
    return str(entity.get("__source") or "") == TAUGHT_CHECKBOX_SOURCE


def _raw_label_span(text: str, label: str) -> tuple[int, int] | None:
    if not label:
        return None
    try:
        match = re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE)
    except re.error:
        match = None
    if match is not None:
        return match.start(), match.end()
    idx = text.lower().find(label.lower())
    if idx < 0:
        return None
    return idx, idx + len(label)


def _ticked_items(line: str, section: FormSection) -> list[FormSchemaItem]:
    if section.section_type == "checkbox_yesno":
        if _yes_no_answer(line) != "yes":
            return []
        return [
            item
            for item in section.items
            if safe_search(item.pattern, line) is not None
        ]
    return [
        item
        for item, checked in item_marks_on_line(line, section.items)
        if checked is True
    ]


def _fact_span(text: str, item: FormSchemaItem) -> tuple[str, tuple[int, int]] | None:
    taught = (item.entity_text or "").strip()
    if taught:
        span = _raw_label_span(text, taught)
        if span is not None:
            return taught, span
    label = (item.pattern or "").strip()
    if not label:
        return None
    span = _raw_label_span(text, label)
    if span is None:
        return None
    return label, span


def _append_seed(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    item: FormSchemaItem,
    schema: FormSchema | None = None,
    section: FormSection | None = None,
) -> None:
    found = _fact_span(text, item)
    if found is None:
        return
    display, span = found
    taught = (item.entity_text or display).strip()
    key = taught.casefold() or display.casefold()
    if key in seen:
        return
    seen.add(key)
    start, end = span
    row: dict[str, Any] = {
        "text": display,
        "entity_text": taught,
        "lookup_term": taught,
        "start": start,
        "end": end,
        "assertion": item.assertion or "present",
        "semantic_tag": item.semantic_tag or "situation",
        "label": item.semantic_tag or "situation",
        "__source": TAUGHT_CHECKBOX_SOURCE,
    }
    taught_ids = _taught_concept_ids(schema, section, item)
    if taught_ids:
        row["concept_id"] = str(taught_ids[0])
    entities.append(row)
    _append_taught_procedure(entities, row, item)


def _append_taught_procedure(
    entities: list[dict[str, Any]],
    fact: dict[str, Any],
    item: FormSchemaItem,
) -> None:
    """Record the test a ticked box says was carried out.

    Some boxes report a finding *and* the investigation that found it:
    "Suspicious pelvic mass on pelvic ultrasound" only gets ticked
    because somebody scanned her. Coding the mass alone leaves the scan
    invisible, and a guideline then asks for a test the form already
    reported.

    The procedure is a second fact over the same span, so it keeps the
    tick's own offsets. ``procedure_snomed`` is taught per item in the
    FormSchema, which is what decides whether a box works this way.
    """
    concept_id = str(item.procedure_snomed or "").strip()
    if not concept_id:
        return
    display = (item.procedure_display or item.entity_text or "").strip()
    entities.append(
        {
            **fact,
            "entity_text": display,
            "lookup_term": display,
            "concept_id": concept_id,
            "semantic_tag": "procedure",
            "label": "procedure",
        }
    )


def _taught_concept_ids(
    schema: FormSchema | None,
    section: FormSection | None,
    item: FormSchemaItem,
) -> list[int]:
    groups = list(getattr(schema, "completeness_groups", None) or [])
    return concept_ids_for_item_pattern(
        groups,
        item_pattern=item.pattern,
        section_id=str(getattr(section, "section_id", "") or ""),
    )


def _seed_line(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    line: str,
    section: FormSection,
    schema: FormSchema,
) -> None:
    if section.section_type not in _CHECKBOX_TYPES:
        return
    for item in _ticked_items(line, section):
        _append_seed(entities, seen, text, item, schema, section)


def _letter_has_section_header(text: str, schema: FormSchema) -> bool:
    return any(
        section.matches_header(line)
        for section in schema.sections
        for line in text.splitlines()
    )


def seed_checkbox_entities(
    encounter_text: str,
    schema: FormSchema,
) -> list[dict[str, Any]]:
    """Return one entity per ticked taught checkbox, at raw offsets."""
    if not encounter_text.strip() or not schema.sections:
        return []
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    lines = encounter_text.splitlines()
    if not _letter_has_section_header(encounter_text, schema):
        for section in schema.sections:
            for line in lines:
                _seed_line(entities, seen, encounter_text, line, section, schema)
        return entities
    current: FormSection | None = None
    for line in lines:
        matched = _find_matching_section(line, schema.sections)
        if matched is not None:
            current = matched
        if current is not None:
            _seed_line(entities, seen, encounter_text, line, current, schema)
    return entities


def _row_key(row: dict[str, Any]) -> str:
    return str(row.get("text") or "").strip().casefold()


def _seed_covers_row(seed_key: str, row_key: str) -> bool:
    """Exact label, or a printed phrase inside a longer extractor span."""
    if not seed_key or not row_key:
        return False
    if seed_key == row_key:
        return True
    if " " not in seed_key:
        return False
    return seed_key in row_key


def merge_checkbox_seed_entities(
    entities: list[dict[str, Any]],
    seeded: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Taught ticks replace same-label or longer same-phrase extractor rows."""
    if not seeded:
        return entities
    covers = [(_row_key(ent), ent) for ent in seeded if _row_key(ent)]
    merged: list[dict[str, Any]] = []
    used: set[int] = set()
    for row in entities:
        if not isinstance(row, dict):
            merged.append(row)
            continue
        cover = (ent for key, ent in covers if _seed_covers_row(key, _row_key(row)))
        match = next(cover, None)
        if match is None:
            merged.append(row)
            continue
        marker = id(match)
        if marker in used:
            continue
        merged.append(match)
        used.add(marker)
    for _key, ent in covers:
        if id(ent) not in used:
            merged.append(ent)
            used.add(id(ent))
    return merged


__all__ = [
    "TAUGHT_CHECKBOX_SOURCE",
    "is_taught_checkbox",
    "merge_checkbox_seed_entities",
    "seed_checkbox_entities",
]
