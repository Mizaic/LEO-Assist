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


def _append_seed(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    item: FormSchemaItem,
) -> None:
    label = (item.pattern or "").strip()
    if not label:
        return
    key = label.casefold()
    if key in seen:
        return
    span = _raw_label_span(text, label)
    if span is None:
        return
    seen.add(key)
    start, end = span
    taught = item.entity_text or label
    entities.append(
        {
            "text": label,
            "entity_text": taught,
            "lookup_term": taught,
            "start": start,
            "end": end,
            "assertion": item.assertion or "present",
            "semantic_tag": item.semantic_tag or "situation",
            "label": item.semantic_tag or "situation",
            "__source": "form_schema_checkbox",
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


__all__ = ["seed_checkbox_entities"]
