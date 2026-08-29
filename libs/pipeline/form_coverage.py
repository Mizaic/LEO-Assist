"""Taught-form coverage: record claimed regions and degrade when unclaimed.

Atlas trace:
  DI: DI-71B94A23
  DO: DO-80754861
  VT: VT-1655FF7B
  Risk: R-7D193158
  Unclaimed narrative still extracts. The run is marked
  form_coverage_incomplete and degraded so a person can see the
  taught form did not cover the letter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from libs.pipeline.form_schema_normalizer import FormSchema, FormSection

_DOC_BANNER_RE = re.compile(r"^---\s*Document:", re.IGNORECASE)
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")


@dataclass(frozen=True)
class ClaimedRegion:
    """One span of lines owned by a taught section."""

    section_id: str
    start_line: int
    end_line: int


@dataclass
class FormCoverageReport:
    """Coverage result for one referral bundle."""

    claimed_regions: list[ClaimedRegion] = field(default_factory=list)
    unclaimed_lines: list[str] = field(default_factory=list)
    incomplete: bool = False


def _is_claimable(line: str) -> bool:
    """True when a line is narrative the form should have claimed."""
    stripped = line.strip()
    if not stripped:
        return False
    if _DOC_BANNER_RE.match(stripped):
        return False
    if _TABLE_SEP_RE.match(stripped):
        return False
    return True


def _matching_section(line: str, sections: list[FormSection]) -> FormSection | None:
    for section in sections:
        if section.matches_header(line):
            return section
    return None


def _close_region(
    claimed: list[ClaimedRegion],
    section_id: str | None,
    start: int | None,
    end: int,
) -> None:
    if section_id is None or start is None:
        return
    claimed.append(ClaimedRegion(section_id, start, end))


def _measure_chunk(
    chunk: str,
    sections: list[FormSection],
    current: FormSection | None,
    line_offset: int,
) -> tuple[list[ClaimedRegion], list[str], FormSection | None, int]:
    """Walk one chunk and return claimed spans, unclaimed lines, and carry."""
    claimed: list[ClaimedRegion] = []
    unclaimed: list[str] = []
    section_id = current.section_id if current else None
    start = line_offset if current is not None else None
    lines = chunk.splitlines()
    for index, line in enumerate(lines):
        abs_index = line_offset + index
        matched = _matching_section(line, sections)
        if matched is not None:
            _close_region(claimed, section_id, start, abs_index)
            current = matched
            section_id = matched.section_id
            start = abs_index
            continue
        if current is None and _is_claimable(line):
            unclaimed.append(line.strip())
    _close_region(claimed, section_id, start, line_offset + len(lines))
    return claimed, unclaimed, current, len(lines)


def measure_form_coverage(
    schema: FormSchema,
    chunks: list[str],
    chunk_section_map: list[dict[str, Any]] | None = None,
) -> FormCoverageReport:
    """Record which taught sections claimed text in ``chunks``."""
    from libs.pipeline.form_schema_normalizer import _resolve_default_sections

    if not chunks:
        return FormCoverageReport()
    defaults = _resolve_default_sections(schema, len(chunks), chunk_section_map or [])
    claimed: list[ClaimedRegion] = []
    unclaimed: list[str] = []
    carried: FormSection | None = None
    line_offset = 0
    for index, chunk in enumerate(chunks):
        current = defaults[index] or carried
        part, leftover, carried, nlines = _measure_chunk(
            chunk, schema.sections, current, line_offset
        )
        claimed.extend(part)
        unclaimed.extend(leftover)
        line_offset += nlines
    return FormCoverageReport(
        claimed_regions=claimed,
        unclaimed_lines=unclaimed,
        incomplete=bool(unclaimed),
    )


def coverage_state_fields(
    schema: FormSchema,
    chunks: list[str],
    chunk_section_map: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pipeline-state keys for a taught-form coverage measurement."""
    report = measure_form_coverage(schema, chunks, chunk_section_map)
    fields: dict[str, Any] = {"form_coverage_incomplete": report.incomplete}
    if report.incomplete:
        fields["degraded"] = True
    return fields
