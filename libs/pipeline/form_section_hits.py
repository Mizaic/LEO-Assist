"""Collect taught-form section hits for completeness.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
  Risk: R-0883B521
  A ticked box is a first-class fact for completeness. Hits travel on
  pipeline state into quality_check. A taught test-table row is filled in
  exactly when it reports a result, the same check that seeds its facts.
"""

from __future__ import annotations

import re
from typing import Any

from libs.pipeline.form_pattern_match import safe_search
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    _resolve_default_sections,
    _yes_no_answer,
)
from libs.pipeline.form_schema_seeding import (
    battery_row_reports_a_result,
    row_matches_battery,
)
from libs.pipeline.form_tick_marks import item_marks_on_line

_BOX_TYPES = frozenset({"checkbox_single", "checkbox_multi", "checkbox_yesno", "scale"})
_FREE_TEXT_TYPES = frozenset({"free_text"})
# A test table's heading line can also be its only result row.
_TEST_TABLE_TYPES = frozenset({"ordered_tests"})
_EMPTY_FREE_TEXT_RE = re.compile(
    r"(?i)^\s*(no information provided|see attachment|not specified)\.?\s*$"
)


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
    relevant = _relevant_hits(member, hits)
    if relevant is None:
        return False, False
    if not relevant:
        return False, False
    return any(bool(hit.get("checked")) for hit in relevant), True


def form_hit_labels(member: dict[str, Any], hits: list[dict[str, Any]]) -> list[str]:
    """Return checked-hit labels that satisfied a form-native member."""
    relevant = _relevant_hits(member, hits)
    if not relevant:
        return []
    labels: list[str] = []
    for hit in relevant:
        if not hit.get("checked"):
            continue
        label = str(hit.get("entity_text") or hit.get("item_pattern") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _relevant_hits(
    member: dict[str, Any], hits: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    section_id = str(member.get("section_id") or "").strip()
    item_pattern = str(member.get("item_pattern") or "").strip()
    if not section_id and not item_pattern:
        return None
    return [hit for hit in hits if _hit_belongs(hit, section_id, item_pattern)]


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
            if current.section_type in _TEST_TABLE_TYPES:
                hits.extend(_test_row_hits(line, current))
            continue
        if current is not None:
            hits.extend(_line_hits(line, current))
    return hits, current


def _line_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    if section.section_type in _BOX_TYPES:
        return _hits_for_line(line, section)
    if section.section_type in _FREE_TEXT_TYPES:
        return _free_text_hits(line, section)
    if section.section_type in _TEST_TABLE_TYPES:
        return _test_row_hits(line, section)
    return []


def _test_row_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    return [
        _hit(section, item, battery_row_reports_a_result(line, item))
        for item in section.items
        if row_matches_battery(line, item)
    ]


def _line_has_content(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    if set(stripped) <= {"-", ":"}:
        return False
    return _EMPTY_FREE_TEXT_RE.match(stripped) is None


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
    return [
        _hit(section, item, checked is True)
        for item, checked in item_marks_on_line(line, section.items)
    ]


def _hit(section: FormSection, item: FormSchemaItem, checked: bool) -> dict[str, Any]:
    return {
        "section_id": section.section_id,
        "item_pattern": item.pattern,
        "entity_text": item.entity_text,
        "checked": checked,
    }


def _yesno_hits(line: str, section: FormSection) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in section.items:
        if safe_search(item.pattern, line) is None:
            continue
        hits.append(_hit(section, item, _yes_no_answer(line) == "yes"))
    return hits
