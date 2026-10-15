"""Deterministic extraction of lab-panel abbreviations from referral documents.

Atlas trace:
  UN: UN-89E2AE36
  Aligns with annotation_guidelines_v1 rule 9 (observable spans).

Template-agnostic: does not depend on ``## Blood Results`` or a single table layout.
Works across the referral templates under ``templates/`` (Word/PDF/SystmOne shapes)
once rendered or pasted into encounter text. Detection uses:

  - Any markdown table cell containing ``abbrev value unit`` clusters
  - Dense lab lines (two or more distinct abbrevs on one line)
  - Lines inside common lab sections (``Blood Tests``, ``Pathology``, etc.)
"""

from __future__ import annotations

import re
from datetime import date
from collections.abc import Callable
from typing import Any

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.blood_panel_presets import battery_for_label

# Display-name abbreviations used across validation scenario fixtures.
_BLOOD_ABBREVS = (
    "Hb",
    "WCC",
    "Plts",
    "MCV",
    "Na",
    "K",
    "Creat",
    "ALT",
    "Alk Phos",
    "Bili",
    "Alb",
    "CRP",
    "ESR",
    "Ferritin",
    "Ca",
    "HbA1c",
    "Iron",
    "TIBC",
    "LDH",
    "PV",
    "eGFR",
    "TSH",
    "Fasting glucose",
    "PSA",
)

_ABBREV_CANONICAL = {abbrev.casefold(): abbrev for abbrev in _BLOOD_ABBREVS}
# Template / EHR spelling variants (e.g. SystmOne ``HBA1c``).
_ABBREV_CANONICAL["hba1c"] = "HbA1c"

_ABBREV_PATTERN = "|".join(
    re.escape(a) for a in sorted(_BLOOD_ABBREVS, key=len, reverse=True)
)

# A reported numeric result, with or without a comparator ("<0.5").
VALUE_PATTERN = r"[<>]?\s*\d+(?:\.\d+)?"
# A unit of measure, including compound blood-count units ("x10^9/L").
UNIT_PATTERN = r"(?:x10\^?\d+/?[A-Za-z]+|[A-Za-z][A-Za-z0-9%/^]+)"

_CELL_PAIR_RE = re.compile(
    rf"\b(?P<name>{_ABBREV_PATTERN})\s+"
    rf"(?P<value>{VALUE_PATTERN})\s*"
    rf"(?P<unit>{UNIT_PATTERN})"
    r"(?=\s*,|\s*\||\s*;|\s|$)",
    re.IGNORECASE,
)

_MIN_DISTINCT_ABBREVS_ON_LINE = 2

# Lines that open a lab-results block in USC / 2WW / site-specific templates.
_LAB_SECTION_LINE_RE = re.compile(
    r"^(?:#+\s*)?(?:"
    r"blood\s+tests?(?:\s*\([^)]*\))?"
    r"|blood\s+results?"
    r"|pathology(?:\s*&\s*radiology)?"
    r"|recent\s+(?:blood|investigations|pathology)"
    r"|pre-ct\s+blood\s+panel"
    r"|investigation\s+findings"
    r")",
    re.IGNORECASE,
)

_MAX_SECTION_CHARS = 12_000


def _canonical_abbrev(name: str) -> str:
    key = name.strip().casefold()
    return _ABBREV_CANONICAL.get(key, name.strip())


def _entity_from_match(
    name: str,
    value: str,
    unit: str,
    *,
    sentence_id: str,
    start: int,
    end: int,
) -> dict[str, Any]:
    clean_name = _canonical_abbrev(name)
    clean_value = re.sub(r"\s+", " ", value).strip()
    clean_unit = re.sub(r"\s*/\s*", "/", (unit or "").strip())
    return {
        "text": clean_name,
        "label": "observable_entity",
        "semantic_tag": "observable entity",
        "start": start,
        "end": end,
        "assertion": "present",
        "confidence": 0.85,
        "normalized": None,
        "value": clean_value or None,
        "unit": clean_unit or None,
        "reference_range": None,
        "__sentence_id": sentence_id,
        "__source": "blood_panel_table",
        "__model_name": "deterministic-fallback",
        "__model_version": "v1",
        "__contract_version": "",
        "__source_meta": {},
        "__relations": [],
    }


def has_value_unit_pair(text: str) -> bool:
    """Return True when *text* holds an ``abbrev value unit`` result cluster."""
    return _CELL_PAIR_RE.search(text) is not None


def _pairs_from_text(text: str) -> list[tuple[str, str, str, int, int]]:
    pairs: list[tuple[str, str, str, int, int]] = []
    for match in _CELL_PAIR_RE.finditer(text):
        name = match.group("name") or ""
        if not name:
            continue
        pairs.append(
            (
                name,
                match.group("value") or "",
                match.group("unit") or "",
                match.start("name"),
                match.end("name"),
            )
        )
    return pairs


def _distinct_abbrev_count(text: str) -> int:
    return len({_canonical_abbrev(p[0]).casefold() for p in _pairs_from_text(text)})


def _is_lab_dense_line(text: str) -> bool:
    return _distinct_abbrev_count(text) >= _MIN_DISTINCT_ABBREVS_ON_LINE


def _append_pairs(
    entities: list[dict[str, Any]],
    seen: set[str],
    text: str,
    *,
    sentence_id: str,
    base_offset: int,
) -> None:
    for name, value, unit, rel_start, rel_end in _pairs_from_text(text):
        key = _canonical_abbrev(name).casefold()
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            _entity_from_match(
                name,
                value,
                unit,
                sentence_id=sentence_id,
                start=base_offset + rel_start,
                end=base_offset + rel_end,
            )
        )


def _is_table_separator_row(line: str) -> bool:
    cells = [part.strip() for part in line.split("|")[1:-1]]
    if not cells:
        return False
    return all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell)


def _line_opens_lab_section(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _LAB_SECTION_LINE_RE.match(stripped):
        return True
    lower = stripped.casefold()
    return "<pathology" in lower and "table" in lower


def _lab_section_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    line_start = 0
    for line in text.splitlines(keepends=True):
        if _line_opens_lab_section(line):
            section_start = line_start
            section_end = min(len(text), section_start + _MAX_SECTION_CHARS)
            rest = text[line_start + len(line) : section_end]
            heading = re.search(r"\n#+\s", rest)
            if heading:
                section_end = line_start + len(line) + heading.start()
            ranges.append((section_start, section_end))
        line_start += len(line)
    return ranges


def _offset_in_line(line: str, index_in_line: int, line_base: int) -> int:
    return line_base + index_in_line


def _scan_table_row_cells(
    line: str,
    line_base: int,
    entities: list[dict[str, Any]],
    seen: set[str],
) -> None:
    if not line.strip().startswith("|") or _is_table_separator_row(line):
        return
    for match in re.finditer(r"\|([^|]*)", line):
        cell = (match.group(1) or "").strip()
        if not cell or not _CELL_PAIR_RE.search(cell):
            continue
        _append_pairs(
            entities,
            seen,
            cell,
            sentence_id="s0",
            base_offset=_offset_in_line(line, match.start(1), line_base),
        )


def _scan_all_markdown_table_cells(
    encounter_text: str, entities: list[dict[str, Any]], seen: set[str]
) -> None:
    offset = 0
    for line in encounter_text.splitlines(keepends=True):
        _scan_table_row_cells(line, offset, entities, seen)
        offset += len(line)


def _scan_dense_lines(encounter_text: str, entities: list, seen: set) -> None:
    offset = 0
    for line in encounter_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and _is_lab_dense_line(stripped):
            line_start = offset + (len(line) - len(line.lstrip()))
            _append_pairs(
                entities,
                seen,
                stripped,
                sentence_id="s0",
                base_offset=line_start,
            )
        offset += len(line)


def _scan_lab_sections(encounter_text: str, entities: list, seen: set) -> None:
    for section_start, section_end in _lab_section_ranges(encounter_text):
        offset = section_start
        section = encounter_text[section_start:section_end]
        for line in section.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("|"):
                _scan_table_row_cells(line, offset, entities, seen)
            elif stripped and _pairs_from_text(stripped):
                line_start = offset + (len(line) - len(line.lstrip()))
                _append_pairs(
                    entities,
                    seen,
                    stripped,
                    sentence_id="s0",
                    base_offset=line_start,
                )
            offset += len(line)


_DATED_TEST_LINE_RE = re.compile(
    r"^[ \t]*(\d{1,2})/(\d{1,2})/(\d{4})[ \t]+(?P<name>\S.*?)[ \t]*$"
)
# A result on its own line: "< 4 ug/g", "36.8 C", "1.9 mg/L".
_LONE_RESULT_RE = re.compile(
    r"^[ \t]*(?P<value>[<>]?[ \t]*\d+(?:\.\d+)?)[ \t]*"
    r"(?P<unit>[A-Za-z%µ][A-Za-z0-9%^µ]*(?:/[A-Za-z0-9%^µ]+)*)[ \t]*$"
)


def _iso_date(day: str, month: str, year: str) -> str:
    """UK ``DD/MM/YYYY`` as an ISO date, or empty when it is not a date."""
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def _result_after(lines: list[str], index: int) -> tuple[str, str]:
    """Return the ``(value, unit)`` printed under a dated test line.

    Only the next non-blank line is considered. A results summary puts
    the number directly beneath its test, and looking further would
    start attaching one test's result to another.
    """
    for line in lines[index + 1 :]:
        if not line.strip():
            continue
        match = _LONE_RESULT_RE.match(line)
        if not match:
            return "", ""
        value = re.sub(r"\s+", " ", match.group("value")).strip()
        return value, match.group("unit")
    return "", ""


def _scan_dated_battery_lines(encounter_text: str, entities: list, seen: set) -> None:
    """Code ``DD/MM/YYYY <test name>`` lines from a plain-text summary.

    Only a line whose name resolves to a known preset battery counts, so
    a dated line about anything else is left alone. That gate is what
    keeps this from inventing tests out of ordinary prose.
    """
    offset = 0
    lines = encounter_text.splitlines()
    for index, line in enumerate(lines):
        match = _DATED_TEST_LINE_RE.match(line)
        if match:
            _append_dated_battery(entities, seen, match, lines, index, offset)
        offset += len(line) + 1


def _append_dated_battery(
    entities: list,
    seen: set,
    match: re.Match,
    lines: list[str],
    index: int,
    offset: int,
) -> None:
    name = match.group("name")
    battery = battery_for_label(name)
    if battery is None or not battery.procedure_snomed:
        return
    key = f"dated:{battery.procedure_snomed}:{offset}"
    if key in seen:
        return
    seen.add(key)
    value, unit = _result_after(lines, index)
    start = offset + match.start("name")
    entities.append(
        {
            "text": name,
            "label": "procedure",
            "semantic_tag": "procedure",
            "concept_id": battery.procedure_snomed,
            "start": start,
            "end": start + len(name),
            "assertion": "present",
            "confidence": 0.85,
            "normalized": None,
            "value": value or None,
            "unit": unit or None,
            "observed_at": _iso_date(*match.group(1, 2, 3)) or None,
            "reference_range": None,
            "__sentence_id": "s0",
            "__source": "blood_panel_dated_line",
            "__model_name": "deterministic-fallback",
            "__model_version": "v1",
            "__contract_version": "",
            "__source_meta": {},
            "__relations": [],
        }
    )


def _scan_dense_chunks(chunks: list[SentenceChunk], entities: list, seen: set) -> None:
    for chunk in chunks:
        text = chunk.text or ""
        if not _is_lab_dense_line(text):
            continue
        _append_pairs(
            entities,
            seen,
            text,
            sentence_id=chunk.sentence_id,
            base_offset=chunk.start,
        )


def extract_blood_panel_table_entities(
    encounter_text: str,
    chunks: list[SentenceChunk],
) -> list[dict[str, Any]]:
    """Return observable abbrev entities from lab tables, sections, and dense lines."""
    text = encounter_text or ""
    if not text.strip() and not chunks:
        return []

    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    if text.strip():
        _scan_all_markdown_table_cells(text, entities, seen)
        _scan_lab_sections(text, entities, seen)
        _scan_dense_lines(text, entities, seen)
        _scan_dated_battery_lines(text, entities, seen)
    _scan_dense_chunks(chunks, entities, seen)
    return entities


def merge_blood_panel_entities(
    entities: list[dict[str, Any]],
    panel_entities: list[dict[str, Any]],
    replaces: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """Add panel entities whose text is not already present.

    Within ``panel_entities`` a procedure and an observable may share a
    text: a single-result row (FIT) seeds both from one label.

    A panel entity for which ``replaces`` is true (a test row taught with
    its code) takes the place of the first fact with the same text and
    kind, and is added even when only a fact of the other kind has its
    text.
    """
    if not panel_entities:
        return entities
    merged = list(entities)
    existing: dict[tuple[str, bool], int] = {}
    for i, ent in enumerate(merged):
        if isinstance(ent, dict) and _text_key(ent):
            existing.setdefault((_text_key(ent), _is_observable(ent)), i)
    texts = {text for text, _ in existing}
    added: set[tuple[str, bool]] = set()
    for ent in panel_entities:
        pair = (_text_key(ent), _is_observable(ent))
        if not pair[0] or pair in added:
            continue
        if replaces is not None and replaces(ent):
            _put_in_place(merged, existing.pop(pair, None), ent)
        elif pair[0] in texts:
            continue
        else:
            merged.append(ent)
        added.add(pair)
    return merged


def _put_in_place(
    merged: list[dict[str, Any]], index: int | None, ent: dict[str, Any]
) -> None:
    if index is None:
        merged.append(ent)
    else:
        merged[index] = ent


def _text_key(entity: dict[str, Any]) -> str:
    return str(entity.get("text") or "").strip().casefold()


def _is_observable(entity: dict[str, Any]) -> bool:
    tag = str(entity.get("semantic_tag") or "").replace("_", " ").casefold()
    return tag == "observable entity"
