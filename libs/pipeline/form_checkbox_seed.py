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

from libs.pipeline.form_pattern_match import safe_search
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    _TICK_BOX_RE,
    _box_is_checked,
    _item_is_checked,
    _items_in_line_order,
    _yes_no_answer,
)

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


def _paired_checked_items(
    line: str, items: list[FormSchemaItem]
) -> list[FormSchemaItem] | None:
    ordered = _items_in_line_order(line, items)
    boxes = list(_TICK_BOX_RE.finditer(line))
    if len(ordered) < 2 or len(boxes) < len(ordered):
        return None
    return [
        item for item, box in zip(ordered, boxes, strict=False) if _box_is_checked(box)
    ]


def _ticked_items(line: str, section: FormSection) -> list[FormSchemaItem]:
    if section.section_type == "checkbox_yesno":
        if _yes_no_answer(line) != "yes":
            return []
        return [
            item
            for item in section.items
            if safe_search(item.pattern, line) is not None
        ]
    paired = _paired_checked_items(line, section.items)
    if paired is not None:
        return paired
    return [item for item in section.items if _item_is_checked(line, item)]


def _fact_span(
    text: str, item: FormSchemaItem
) -> tuple[str, tuple[int, int]] | None:
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
    entities.append(
        {
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
    for section in schema.sections:
        if section.section_type not in _CHECKBOX_TYPES:
            continue
        for line in encounter_text.splitlines():
            for item in _ticked_items(line, section):
                _append_seed(entities, seen, encounter_text, item)
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
        cover = (
            ent
            for key, ent in covers
            if _seed_covers_row(key, _row_key(row))
        )
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
