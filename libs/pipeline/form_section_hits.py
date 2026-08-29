"""Collect taught-form section hits for completeness.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
  Risk: R-0883B521
  A ticked box is a first-class fact for completeness. Hits travel on
  pipeline state into quality_check.
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.form_pattern_match import safe_search
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    _box_is_checked,
    _item_is_checked,
    _items_in_line_order,
    _resolve_default_sections,
    _TICK_BOX_RE,
    _yes_no_answer,
)

_BOX_TYPES = frozenset({"checkbox_single", "checkbox_multi", "checkbox_yesno", "scale"})
_FREE_TEXT_TYPES = frozenset({"free_text"})


def collect_section_hits(
    schema: FormSchema,
    chunks: list[str],
    chunk_section_map: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return one hit per taught box seen in ``chunks``."""
    if not chunks or not schema.sections:
        return []
    defaults = _resolve_default_sections(schema, len(chunks), chunk_section_map or [])
    hits: list[dict[str, Any]] = []
    carried: FormSection | None = None
    for index, chunk in enumerate(chunks):
        part, carried = _hits_for_chunk(
            chunk, schema.sections, defaults[index] or carried
        )
        hits.extend(part)
    return hits


def form_hit_result(
    member: dict[str, Any], hits: list[dict[str, Any]]
) -> tuple[bool, bool]:
    """Return (matched, assessable) for a form-native member."""
    section_id = str(member.get("section_id") or "").strip()
    item_pattern = str(member.get("item_pattern") or "").strip()
    if not section_id and not item_pattern:
        return False, False
    relevant = [hit for hit in hits if _hit_belongs(hit, section_id, item_pattern)]
    if not relevant:
        return False, False
    return any(bool(hit.get("checked")) for hit in relevant), True


def _hit_belongs(hit: dict[str, Any], section_id: str, item_pattern: str) -> bool:
    if section_id and str(hit.get("section_id") or "") != section_id:
        return False
    if item_pattern and str(hit.get("item_pattern") or "") != item_pattern:
        return False
    return True


def _hits_for_chunk(
    chunk: str,
    sections: list[FormSection],
    current: FormSection | None,
) -> tuple[list[dict[str, Any]], FormSection | None]:
    hits: list[dict[str, Any]] = []
    for line in chunk.splitlines():
        matched = _matching_section(line, sections)
        if matched is not None:
            current = matched
            continue
        if current is None:
            continue
        if current.section_type in _BOX_TYPES:
            hits.extend(_hits_for_line(line, current))
        elif current.section_type in _FREE_TEXT_TYPES:
            hits.extend(_free_text_hits(line, current))
    return hits, current


def _line_has_content(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    return not set(stripped) <= {"-", ":"}


def _free_text_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    if not _line_has_content(line):
        return []
    item = (
        section.items[0]
        if section.items
        else FormSchemaItem(pattern="", entity_text=section.label)
    )
    return [_hit(section, item, True)]


def _matching_section(line: str, sections: list[FormSection]) -> FormSection | None:
    for section in sections:
        if section.matches_header(line):
            return section
    return None


def _hits_for_line(line: str, section: FormSection) -> list[dict[str, Any]]:
    if section.section_type == "checkbox_yesno":
        return _yesno_hits(line, section)
    packed = _packed_hits(line, section)
    if packed is not None:
        return packed
    return _per_item_hits(line, section)


def _hit(section: FormSection, item: FormSchemaItem, checked: bool) -> dict[str, Any]:
    return {
        "section_id": section.section_id,
        "item_pattern": item.pattern,
        "entity_text": item.entity_text,
        "checked": checked,
    }


def _packed_hits(line: str, section: FormSection) -> list[dict[str, Any]] | None:
    ordered = _items_in_line_order(line, section.items)
    boxes = list(_TICK_BOX_RE.finditer(line))
    if len(ordered) < 2 or len(boxes) < len(ordered):
        return None
    return [
        _hit(section, item, _box_is_checked(box))
        for item, box in zip(ordered, boxes, strict=False)
    ]


def _per_item_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in section.items:
        checked = _item_is_checked(line, item)
        if checked is None:
            continue
        hits.append(_hit(section, item, checked))
    return hits


def _yesno_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in section.items:
        if safe_search(item.pattern, line) is None:
            continue
        hits.append(_hit(section, item, _yes_no_answer(line) == "yes"))
    return hits
