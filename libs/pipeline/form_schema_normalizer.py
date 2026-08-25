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
from typing import Literal

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER

SectionType = Literal[
    "checkbox_single",
    "checkbox_yesno",
    "checkbox_multi",
    "free_text",
    "scale",
    "ordered_tests",
    "admin",
    "template_noise",
]

_CHECKED_RE = re.compile(r"\[(?:X|x|\*|YES|yes)\]|\((?:X|x)\)")
_UNCHECKED_RE = re.compile(r"\[\s*\]|\(\s*\)")
_YES_CHECKED_RE = re.compile(r"Yes\s*\[(?:X|x|\*)\]", re.IGNORECASE)
_NO_CHECKED_RE = re.compile(r"No\s*\[(?:X|x|\*)\]", re.IGNORECASE)


@dataclass
class FormSchemaItem:
    """One checkbox/option within a form section."""

    pattern: str
    entity_text: str
    semantic_tag: str = "finding"
    assertion: str = "present"


@dataclass
class FormSection:
    """One logical section of a form."""

    section_id: str
    section_type: SectionType
    label: str
    start_pattern: str
    items: list[FormSchemaItem] = field(default_factory=list)

    def matches_header(self, line: str) -> bool:
        return bool(re.search(self.start_pattern, line, re.IGNORECASE))


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


def _mark(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return line
    return f"{NON_EXTRACTABLE_MARKER} {stripped}"


def _has_any_box(line: str) -> bool:
    return bool(_CHECKED_RE.search(line) or _UNCHECKED_RE.search(line))


def _item_is_checked(line: str, item: FormSchemaItem) -> bool | None:
    """Return True if item is checked, False if unchecked, None if not found."""
    match = re.search(item.pattern, line, re.IGNORECASE)
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


def _process_yesno_line(line: str, section: FormSection) -> list[str]:
    """Handle one line for checkbox_yesno."""
    for item in section.items:
        if not re.search(item.pattern, line, re.IGNORECASE):
            continue
        if _YES_CHECKED_RE.search(line):
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


def _process_section_lines(lines: list[str], section: FormSection) -> list[str]:
    """Apply section-type rules to lines that belong to this section."""
    stype = section.section_type
    if stype in ("admin", "template_noise", "ordered_tests"):
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

    lines = text.splitlines()
    out: list[str] = []
    current_section: FormSection | None = None
    pending: list[str] = []

    def _flush(section: FormSection | None, buf: list[str]) -> None:
        if section is None:
            out.extend(buf)
        else:
            out.extend(_process_section_lines(buf, section))
        buf.clear()

    for line in lines:
        matched = _find_matching_section(line, schema.sections)
        if matched is not None:
            _flush(current_section, pending)
            current_section = matched
            out.append(line)
        else:
            pending.append(line)

    _flush(current_section, pending)
    return "\n".join(out)


def _find_matching_section(
    line: str, sections: list[FormSection]
) -> FormSection | None:
    for section in sections:
        if section.matches_header(line):
            return section
    return None
