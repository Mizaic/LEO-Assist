"""Deterministic section splitter for referral form teaching.

Finds Section A/B/C and named admin headers even when they sit
inside markdown tables or HTML cells. Used when the LLM returns
nothing useful.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import re
from typing import Any

_SECTION = re.compile(r"(?i)^section\s+([a-z])\b")
_NAMED = re.compile(
    r"(?i)^(patient details|practice details|minimum dataset|"
    r"for trust use|hospital number)"
)
_CHECKED = re.compile(r"\[(?:X|x|\*)\]")
_UNCHECKED = re.compile(r"\[\s*\]")
_YES_NO = re.compile(r"Yes\s*\[(?:X|x)?\s*\]\s*No\s*\[(?:X|x)?\s*\]", re.I)
_SCALE = re.compile(r"\b1\.\s+\w[\w\s]+\[(?:X|\s*)\]")
_TESTS = re.compile(
    r"mandatory|fbc|lft|ues|urea|calcium|creatinine|blood\s+results?", re.I
)
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"(?i)<br\s*/?>|</(?:p|div|tr|h[1-6]|li)>")
_TD = re.compile(r"(?i)</td>")
_LEAD_PIPE = re.compile(r"(?m)^\s*\|\s*")
_TAIL_PIPE = re.compile(r"(?m)\s*\|\s*$")
_SECTION_SPLIT = re.compile(r"(?i)(?<![A-Za-z])(section\s+[a-z]\b)")


def normalize_form_text(text: str) -> str:
    """Turn HTML / table markup into line-oriented form text."""
    cleaned = (text or "").replace("\r\n", "\n")
    cleaned = _BLOCK.sub("\n", cleaned)
    cleaned = _TD.sub(" | ", cleaned)
    cleaned = _TAG.sub(" ", cleaned)
    cleaned = _LEAD_PIPE.sub("", cleaned)
    cleaned = _TAIL_PIPE.sub("", cleaned)
    cleaned = _SECTION_SPLIT.sub(r"\n\1", cleaned)
    return re.sub(r"[ \t]+", " ", cleaned)


def split_form_sections(text: str) -> list[dict[str, Any]]:
    """Propose FormSchema sections from raw or table-wrapped form text."""
    lines = normalize_form_text(text).split("\n")
    breaks = _breakpoints(lines)
    if not breaks:
        return []
    sections: list[dict[str, Any]] = []
    for i, (idx, label) in enumerate(breaks):
        next_idx = breaks[i + 1][0] if i + 1 < len(breaks) else len(lines)
        body = [ln.strip() for ln in lines[idx + 1 : next_idx] if ln.strip()]
        section_type = "admin" if _NAMED.match(label) else _classify(body)
        letter = _SECTION.match(label)
        section_id = letter.group(1).upper() if letter else str(i)
        sections.append(
            {
                "section_id": section_id,
                "label": label,
                "section_type": section_type,
                "start_pattern": _start_pattern(label),
                "items": _items(section_type, body),
            }
        )
    return sections


def is_incomplete_schema(sections: list[dict[str, Any]]) -> bool:
    """True when there are no clinical sections to teach."""
    if not sections:
        return True
    skip = {"admin", "template_noise"}
    return all(str(s.get("section_type") or "") in skip for s in sections)


def _breakpoints(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        label = raw.replace("#", " ").strip()
        if not label:
            continue
        if _SECTION.match(label) or _NAMED.match(label):
            found.append((idx, label))
    return found


def _classify(lines: list[str]) -> str:
    if any(_TESTS.search(ln) for ln in lines):
        return "ordered_tests"
    checked = sum(1 for ln in lines if _CHECKED.search(ln))
    unchecked = sum(1 for ln in lines if _UNCHECKED.search(ln))
    if checked + unchecked == 0:
        return "free_text"
    if any(_YES_NO.search(ln) for ln in lines):
        return "checkbox_yesno"
    if any(_SCALE.search(ln) for ln in lines):
        return "scale"
    if unchecked > 0 and checked <= 1:
        return "checkbox_single"
    if checked > 1:
        return "checkbox_multi"
    return "checkbox_single"


def _start_pattern(label: str) -> str:
    letter = _SECTION.match(label)
    if letter:
        return rf"(?i)section\s+{letter.group(1).lower()}:"
    first = r"\s+".join(label.split()[:3])
    return rf"(?i){first}"


def _items(section_type: str, body: list[str]) -> list[dict[str, Any]]:
    if section_type not in {"checkbox_single", "checkbox_multi"}:
        return []
    item_re = re.compile(r"([A-Za-z][A-Za-z\s]{1,40}?)\s*\[(?:X|x|\*|\s*)\]")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ln in body:
        for match in item_re.finditer(ln):
            label = re.sub(r"^\d+[.)]\s*", "", match.group(1)).strip()
            if len(label) < 2 or label in seen:
                continue
            seen.add(label)
            items.append(
                {
                    "pattern": label,
                    "entity_text": f"{label} (checked on referral form)",
                    "semantic_tag": "finding",
                    "assertion": "present",
                }
            )
    return items
