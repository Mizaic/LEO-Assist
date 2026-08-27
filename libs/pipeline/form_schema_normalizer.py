"""Per-form schema normaliser for structured referral form text.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)

Once a :FormSchema exists for a form fingerprint, this module rewrites
form text deterministically before LLM extraction:
- Checked checkbox items become clinical entity sentences.
- Unchecked items and noise sections are marked NON_EXTRACTABLE.
- Free-text sections are left unchanged.
- The quality gate is bypassed (score = 1.0) when a schema is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_pattern_match import safe_search, section_matches

SectionType = Literal[
    "checkbox_single",
    "checkbox_yesno",
    "checkbox_multi",
    "free_text",
    "scale",
    "ordered_tests",
    "admin",
    "template_noise",
    "observable",
]

# Default SNOMED semantic tags for each section type archetype.
# Each entry is a list; sections like blood results may carry multiple tags.
SECTION_TYPE_SEMANTIC_TAG: dict[str, list[str]] = {
    "admin": ["none"],
    "template_noise": ["none"],
    "checkbox_single": ["situation"],
    "checkbox_yesno": ["finding"],
    "checkbox_multi": ["finding"],
    "free_text": ["finding"],
    "scale": ["observable"],
    "ordered_tests": ["procedure"],
    "observable": ["observable"],
}

_CHECKED_RE = re.compile(r"\[(?:X|x|\*|YES|yes)\]|\((?:X|x)\)")
_UNCHECKED_RE = re.compile(r"\[\s*\]|\(\s*\)")
# Yes / No rows appear in both box orders on NHS forms: "Yes [X] No [ ]"
# and "[X] Yes [ ] No". Capture the word and its own box either way so a
# tick before the word is not mistaken for an unanswered row.
_YESNO_PAIR_RE = re.compile(
    r"\b(Yes|No)\b\s*\[([^\]]*)\]|\[([^\]]*)\]\s*\b(Yes|No)\b",
    re.IGNORECASE,
)
_BOX_CHECKED_RE = re.compile(r"^(?:[Xx*]|YES|yes)")


@dataclass
class FormSchemaItem:
    """One checkbox/option within a form section."""

    pattern: str
    entity_text: str
    semantic_tag: str = "finding"
    assertion: str = "present"
    # ordered_tests enrichment fields
    procedure_snomed: str = ""
    procedure_display: str = ""
    analytes: list[dict[str, str]] = field(default_factory=list)
    value_placeholder: str = ""


@dataclass
class FormSection:
    """One logical section of a form."""

    section_id: str
    section_type: SectionType
    label: str
    start_pattern: str
    items: list[FormSchemaItem] = field(default_factory=list)
    semantic_tags: list[str] = field(default_factory=lambda: ["finding"])

    def matches_header(self, line: str) -> bool:
        """Return True when *line* is this section's heading row.

        Headings usually sit inside a markdown table cell. Separator rows
        never start a section, and a taught pattern that will not compile
        falls back to a literal match rather than raising.
        """
        return section_matches(self.start_pattern, line)


@dataclass
class FormSchema:
    """Per-form schema recipe stored in Neo4j as :FormSchema."""

    schema_id: str
    fingerprint: str
    form_name: str
    sections: list[FormSection]
    created_by: str
    version: int = 1
    status: str = "active"
    created_at: str = ""
    organization_id: str = ""
    service_id: str = ""
    chunk_section_map: list[dict[str, Any]] = field(default_factory=list)


def _mark(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return line
    return f"{NON_EXTRACTABLE_MARKER} {stripped}"


def _has_any_box(line: str) -> bool:
    return bool(_CHECKED_RE.search(line) or _UNCHECKED_RE.search(line))


def _item_is_checked(line: str, item: FormSchemaItem) -> bool | None:
    """Return True if item is checked, False if unchecked, None if not found."""
    match = safe_search(item.pattern, line)
    if match is None:
        return None
    after = line[match.start() :]
    box_match = re.search(r"\[([^\]]*)\]|\(([^)]*)\)", after)
    if box_match is None:
        return None
    content = (box_match.group(1) or box_match.group(2) or "").strip()
    return bool(re.match(r"[Xx*]|YES|yes", content))


def _process_checkbox_line(line: str, section: FormSection) -> list[str]:
    """Handle one line for checkbox_single or checkbox_multi."""
    if not _has_any_box(line):
        return [line]
    entity_lines: list[str] = []
    found_any = False
    for item in section.items:
        checked = _item_is_checked(line, item)
        if checked is None:
            continue
        found_any = True
        if checked:
            entity_lines.append(item.entity_text)
    if found_any:
        return entity_lines + [_mark(line)]
    if _has_any_box(line):
        return [_mark(line)]
    return [line]


def _yes_no_answer(line: str) -> str | None:
    """Return "yes", "no", or None for a Yes / No row.

    Reads both box orders, so "[X] Yes [ ] No" answers Yes just like
    "Yes [X] No [ ]". Returns None when the row has no single clear
    answer, so an unanswered or contradictory row is never read as Yes.
    """
    checked: set[str] = set()
    found = False
    for match in _YESNO_PAIR_RE.finditer(line):
        word = (match.group(1) or match.group(4) or "").lower()
        if not word:
            continue
        found = True
        box = (match.group(2) if match.group(1) else match.group(3)) or ""
        if _BOX_CHECKED_RE.match(box.strip()):
            checked.add(word)
    if not found or len(checked) != 1:
        return None
    return checked.pop()


def _process_yesno_line(line: str, section: FormSection) -> list[str]:
    """Handle one line for checkbox_yesno."""
    for item in section.items:
        if safe_search(item.pattern, line) is None:
            continue
        if _yes_no_answer(line) == "yes":
            return [item.entity_text, _mark(line)]
        return [_mark(line)]
    if _has_any_box(line):
        return [_mark(line)]
    return [line]


def _process_scale_line(line: str, section: FormSection) -> list[str]:
    """Handle one line for scale."""
    if not _has_any_box(line):
        return [line]
    for item in section.items:
        if _item_is_checked(line, item):
            return [item.entity_text, _mark(line)]
    return [_mark(line)]


def _item_has_taught_analytes(item: FormSchemaItem) -> bool:
    return any(str(a.get("snomed_code") or "").strip() for a in item.analytes)


def _section_has_taught_analytes(section: FormSection) -> bool:
    return any(_item_has_taught_analytes(item) for item in section.items)


def _match_ordered_test_item(
    line: str, items: list[FormSchemaItem]
) -> FormSchemaItem | None:
    for item in items:
        if item.pattern and safe_search(item.pattern, line) is not None:
            return item
    return None


def _match_ordered_test_items(
    line: str, items: list[FormSchemaItem]
) -> list[FormSchemaItem]:
    """Return every taught battery on one row, in taught order.

    The blood results table puts two batteries on a single row, for
    example "| CRP | | | ESR | |". Matching only the first battery loses
    the second one and all of its analytes.
    """
    return [
        item
        for item in items
        if item.pattern and safe_search(item.pattern, line) is not None
    ]


def _process_ordered_tests_lines(lines: list[str], section: FormSection) -> list[str]:
    """Expand taught blood rows; suppress admin boilerplate when no analytes."""
    if not _section_has_taught_analytes(section):
        return [_mark(ln) if ln.strip() else ln for ln in lines]

    from libs.pipeline.form_schema_template import expand_ordered_tests_row

    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        taught = [
            item
            for item in _match_ordered_test_items(ln, section.items)
            if _item_has_taught_analytes(item)
        ]
        if taught:
            out.extend(expand_ordered_tests_row(item) for item in taught)
            continue
        out.append(_mark(ln))
    return out


def _process_section_lines(lines: list[str], section: FormSection) -> list[str]:
    """Apply section-type rules to lines that belong to this section."""
    stype = section.section_type
    if stype == "ordered_tests":
        return _process_ordered_tests_lines(lines, section)
    if stype in ("admin", "template_noise"):
        return [_mark(ln) if ln.strip() else ln for ln in lines]
    if stype == "free_text":
        return list(lines)
    out: list[str] = []
    for ln in lines:
        if stype in ("checkbox_single", "checkbox_multi"):
            out.extend(_process_checkbox_line(ln, section))
        elif stype == "checkbox_yesno":
            out.extend(_process_yesno_line(ln, section))
        elif stype == "scale":
            out.extend(_process_scale_line(ln, section))
        else:
            out.append(ln)
    return out


def apply_schema_to_text(text: str, schema: FormSchema) -> str:
    """Rewrite ``text`` according to ``schema`` for LLM extraction input.

    Lines before the first recognised section header are passed through
    unchanged. Each section is processed according to its ``section_type``.
    """
    if not text:
        return text
    if not schema.sections:
        return text
    return _apply_chunk_text(text, schema.sections, default_section=None)


def _apply_chunk_text(
    chunk: str,
    sections: list[FormSection],
    default_section: FormSection | None,
) -> str:
    """Apply schema rules to one text block."""
    text, _ = _apply_chunk_text_stateful(chunk, sections, default_section)
    return text


def _apply_chunk_text_stateful(
    chunk: str,
    sections: list[FormSection],
    default_section: FormSection | None,
) -> tuple[str, FormSection | None]:
    """Apply schema rules to one block and return the section left active.

    NHS forms often place a free-text label on one line and the clinical
    narrative in a box on the following lines inside the same paragraph
    chunk. Any interior header still starts a new section so body lines
    are not processed as admin or checkbox noise. The trailing section is
    returned so it can carry into the next chunk.
    """
    if not chunk:
        return chunk, default_section
    lines = chunk.splitlines()
    out: list[str] = []
    current_section: FormSection | None = default_section
    pending: list[str] = []

    def _flush() -> None:
        nonlocal pending
        if not pending:
            return
        if current_section is None:
            out.extend(pending)
        else:
            out.extend(_process_section_lines(pending, current_section))
        pending = []

    for line in lines:
        matched = _find_matching_section(line, sections)
        if matched is not None:
            _flush()
            current_section = matched
            out.append(line)
        else:
            pending.append(line)
    _flush()
    return "\n".join(out), current_section


def _find_matching_section(
    line: str, sections: list[FormSection]
) -> FormSection | None:
    for section in sections:
        if section.matches_header(line):
            return section
    return None


def apply_schema_analyte_codes(
    entities: list[dict[str, Any]],
    schema: FormSchema,
    chunk_section_map: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Override inferred observable SNOMED codes with taught analyte codes.

    For each entity whose label matches an analyte in a taught
    ``ordered_tests`` section, replaces the entity's ``snomed_code``
    with the taught value.  Entities with no matching taught code are
    returned unchanged.

    Args:
        entities: Extracted entity dicts (each must have ``label`` and
            ``snomed_code`` keys).
        schema: The FormSchema containing the taught analyte lists.
        chunk_section_map: ``{chunk_idx, section_id}`` map used to scope
            which sections are active for the current document chunks.

    Returns:
        A new list of entity dicts (originals are not mutated).
    """
    taught_codes = _build_analyte_code_index(schema, chunk_section_map)
    if not taught_codes:
        return list(entities)
    return [_apply_code(e, taught_codes) for e in entities]


def _build_analyte_code_index(
    schema: FormSchema,
    chunk_section_map: list[dict[str, Any]],
) -> dict[str, str]:
    """Build a label -> snomed_code lookup from active ordered_tests sections."""
    active_ids = (
        {entry.get("section_id") for entry in chunk_section_map}
        if chunk_section_map
        else None
    )
    codes: dict[str, str] = {}
    for section in schema.sections:
        if section.section_type != "ordered_tests":
            continue
        if active_ids is not None and section.section_id not in active_ids:
            continue
        for item in section.items:
            for analyte in item.analytes:
                label = analyte.get("label", "")
                code = analyte.get("snomed_code", "")
                if label and code:
                    codes[label] = code
    return codes


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


def _battery_present_in_text(text: str, item: FormSchemaItem) -> bool:
    if not item.pattern:
        return False
    for line in text.splitlines():
        if _match_ordered_test_item(line, [item]) is not None:
            return True
    return False


def _seed_battery_entity(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    item: FormSchemaItem,
) -> None:
    label = (item.pattern or item.entity_text or "").strip()
    if not label:
        return
    key = label.casefold()
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
            "start": start,
            "end": end,
            "assertion": item.assertion or "present",
            "semantic_tag": item.semantic_tag or "procedure",
            "__source": "form_schema_ordered_tests",
        }
    )


def _seed_analyte_entity(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    analyte: dict[str, str],
    item: FormSchemaItem,
) -> None:
    label = str(analyte.get("label") or "").strip()
    code = str(analyte.get("snomed_code") or "").strip()
    if not label:
        return
    key = label.casefold()
    if key in seen:
        return
    seen.add(key)
    start, end = _find_label_span(text, label)
    entities.append(
        {
            "text": label,
            "label": label,
            "snomed_code": code,
            "start": start,
            "end": end,
            "assertion": item.assertion or "present",
            "semantic_tag": "observable entity",
            "__source": "form_schema_ordered_tests",
        }
    )


def seed_ordered_tests_entities(
    encounter_text: str,
    schema: FormSchema,
) -> list[dict[str, Any]]:
    """Seed procedure and analyte entities from taught ordered_tests batteries."""
    if not encounter_text.strip() or not schema.sections:
        return []
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in schema.sections:
        if section.section_type != "ordered_tests":
            continue
        for item in section.items:
            if not _battery_present_in_text(encounter_text, item):
                continue
            _seed_battery_entity(entities, seen, encounter_text, item)
            for analyte in item.analytes:
                _seed_analyte_entity(entities, seen, encounter_text, analyte, item)
    return entities


def _apply_code(entity: dict[str, Any], taught_codes: dict[str, str]) -> dict[str, Any]:
    """Return a copy of entity with snomed_code replaced if a taught code exists."""
    label = entity.get("label", "")
    code = taught_codes.get(label)
    if code is None:
        return dict(entity)
    return {**entity, "snomed_code": code}


def normalise_with_schema(
    schema: FormSchema,
    chunks: list[str],
    chunk_section_map: list[dict[str, Any]] | None = None,
) -> str:
    """Normalise ``chunks`` using ``schema`` and join them into one string.

    Prefer :func:`normalise_chunks_with_schema` when the caller needs the
    result per chunk. Chunks contain blank lines, so a joined result
    cannot be split back into the original chunks.
    """
    if not chunks:
        return ""
    return "\n\n".join(
        normalise_chunks_with_schema(schema, chunks, chunk_section_map)
    )


def normalise_chunks_with_schema(
    schema: FormSchema,
    chunks: list[str],
    chunk_section_map: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return one normalised string per chunk, guided by an optional map.

    Args:
        schema: The FormSchema with section rules.
        chunks: Text chunks in stored order, one per document segment.
        chunk_section_map: Optional ``{chunk_idx, section_id}`` entries.
            Entries with no ``chunk_idx`` bind to their own position in
            the list. A map whose indexes do not fit ``chunks`` is
            ignored, because it was built over a different segmentation.

    Returns:
        A list the same length as ``chunks``.
    """
    if not chunks:
        return []
    if not schema.sections:
        return list(chunks)
    defaults = _resolve_default_sections(schema, len(chunks), chunk_section_map or [])
    out: list[str] = []
    carried: FormSection | None = None
    for idx, chunk in enumerate(chunks):
        text, carried = _apply_chunk_text_stateful(
            chunk, schema.sections, defaults[idx] or carried
        )
        out.append(text)
    return out


def _map_index(entry: dict[str, Any], position: int) -> int:
    """Return the chunk index for a map entry, falling back to its order.

    Stored chunks carry no ``chunk_idx``, so a null value means "the
    chunk in this position".
    """
    raw = entry.get("chunk_idx")
    if raw is None:
        return position
    try:
        return int(raw)
    except (TypeError, ValueError):
        return position


def _resolve_default_sections(
    schema: FormSchema,
    chunk_count: int,
    chunk_section_map: list[dict[str, Any]],
) -> list[FormSection | None]:
    """Resolve one default section per chunk from ``chunk_section_map``."""
    defaults: list[FormSection | None] = [None] * chunk_count
    if not chunk_section_map:
        return defaults
    section_by_id = {s.section_id: s for s in schema.sections}
    resolved: list[tuple[int, str]] = []
    for position, entry in enumerate(chunk_section_map):
        idx = _map_index(entry, position)
        if idx < 0 or idx >= chunk_count:
            # The map was built over a different segmentation of the
            # letter. Applying it positionally would route clinical
            # chunks into admin sections, so ignore it and rely on the
            # section headings inside each chunk.
            return [None] * chunk_count
        resolved.append((idx, str(entry.get("section_id") or "")))
    for idx, section_id in resolved:
        defaults[idx] = section_by_id.get(section_id)
    return defaults
