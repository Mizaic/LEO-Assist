"""Fill skipped form sections with their printed tick boxes.

Auto-detect leaves admin and template guidance sections without items,
because nothing in them is coded. The recogniser still counts every tick
box on the letter, so a form taught that way did not match its own
letter. This adds each box label under a skipped section as an item of
that section. The normaliser masks every line of a skipped section, so
these items never become patient facts.

Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1.
Risk R-B88CCFD6.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterator

from libs.form_recognition.anchors import is_usable_anchor
from libs.form_recognition.normalise import (
    normalise_text,
    segments,
    split_at_first_box,
)
from libs.pipeline.form_pattern_match import section_matches

SKIP_SECTION_TYPES = frozenset({"admin", "template_noise"})

_MARKUP_RE = re.compile(r"[*_`]+")
# A label ends at its answer: "Pt Contacted Y [ ] /N [ ]" is "Pt Contacted".
_TRAILING_ANSWER_RE = re.compile(r"(?:\s*[:?/.,;\-]|\s+(?:y|n|yes|no))\s*$", re.I)

Section = dict[str, Any]


def fill_skip_section_boxes(sections: list[Section], source_text: str) -> list[Section]:
    """Return a copy of *sections* with skipped sections' box labels as items.

    Only ``admin`` and ``template_noise`` sections change. A label is the
    printed text before the first box, so an answer typed after the box
    is never stored.
    """
    filled = copy.deepcopy(sections)
    for section, line in _lines_by_section(filled, source_text or ""):
        if section.get("section_type") not in SKIP_SECTION_TYPES:
            continue
        for label in _box_labels(line):
            _add_item(section, label)
    return filled


def _start(section: Section) -> str:
    for key in ("start_pattern", "label", "section_id"):
        value = str(section.get(key) or "").strip()
        if value:
            return value
    return ""


def _lines_by_section(
    sections: list[Section], text: str
) -> Iterator[tuple[Section, str]]:
    """Yield each line with the section it falls under, as the normaliser does."""
    current: Section | None = None
    for line in text.splitlines():
        matched = next((s for s in sections if section_matches(_start(s), line)), None)
        if matched is not None:
            current = matched
        if current is not None:
            yield current, line


def _box_labels(line: str) -> Iterator[str]:
    for segment in segments(line):
        if not (segment.has_box and segment.is_clinical_structure()):
            continue
        label = printed_label(segment.raw)
        if label:
            yield label


def printed_label(cell: str) -> str:
    """Return the printed label of one cell, cut before its first tick box.

    Returns "" when the cell has no label a form could be matched on.
    """
    before, after = split_at_first_box(cell)
    label = _clean(before) or _clean(split_at_first_box(after)[0])
    return label if is_usable_anchor(normalise_text(label)) else ""


def _clean(text: str) -> str:
    cleaned = _MARKUP_RE.sub("", text).strip().lstrip("#").strip()
    while True:
        shorter = _TRAILING_ANSWER_RE.sub("", cleaned).strip()
        if shorter == cleaned:
            return cleaned
        cleaned = shorter


def _pattern_key(item: object) -> str:
    pattern = item.get("pattern") if isinstance(item, dict) else ""
    return normalise_text(str(pattern or ""))


def _add_item(section: Section, label: str) -> None:
    items = list(section.get("items") or [])
    if normalise_text(label) not in {_pattern_key(i) for i in items}:
        items.append(
            {
                "pattern": label,
                "entity_text": label,
                "semantic_tag": "none",
                "assertion": "present",
            }
        )
    section["items"] = items
