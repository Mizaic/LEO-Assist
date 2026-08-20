"""Generic referral-form layout rules (inline boxes, instructions, empty labs).

Atlas trace:
  DI: DI-5C9CA57B
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-5C9CA57B")
"""

from __future__ import annotations

import re

NON_EXTRACTABLE_MARKER = "[NON_EXTRACTABLE]"
_CHECKED = re.compile(r"\[(?:X|x)\]")
_UNCHECKED = re.compile(r"\[\s*\]")

_INLINE_PAIR = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 /+.'-]{0,48}?)\s+" r"(?P<box>\[\s*\]|\[(?:X|x)\])"
)
_YES_NO = re.compile(
    r"(?P<crit>.+?)\s*\|\s*Yes\s+(?P<yes>\[\s*\]|\[(?:X|x)\])\s+"
    r"No\s+(?P<no>\[\s*\]|\[(?:X|x)\])",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(r"(?i)^\s*(\(|please\s+(put|take|ensure|confirm|only\s+use))")
_ADMIN_LINE = re.compile(
    r"(?i)^\s*(does the patient|has the patient been told|"
    r"is the patient aware|holiday plans)"
)
_LAB_ABBREV = re.compile(
    r"\b(Hb|WCC|Plts|MCV|Neut|Na|K|Urea|Creat|eGFR|ALT|Bili|Alb|CRP|ESR)\b",
    re.IGNORECASE,
)
_HAS_DIGIT = re.compile(r"\d")


def _mark(text: str) -> str:
    stripped = text.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return text
    return f"{NON_EXTRACTABLE_MARKER} {stripped}"


def _is_checked(box: str) -> bool:
    return bool(_CHECKED.search(box)) and not (
        _UNCHECKED.search(box) and not _CHECKED.search(box)
    )


def _split_inline_options(line: str) -> str | None:
    pairs = list(_INLINE_PAIR.finditer(line))
    if len(pairs) < 2:
        return None
    pieces: list[str] = []
    for match in pairs:
        cell = f"{match.group('label').strip()} {match.group('box')}"
        if _is_checked(match.group("box")):
            pieces.append(cell)
        else:
            pieces.append(_mark(cell))
    return " | ".join(pieces)


def _normalise_yes_no_row(line: str) -> str | None:
    match = _YES_NO.search(line)
    if not match:
        return None
    yes_checked = _is_checked(match.group("yes"))
    if yes_checked:
        return match.group("crit").strip()
    return _mark(line)


def _is_empty_lab_line(line: str) -> bool:
    if _HAS_DIGIT.search(line):
        return False
    names = _LAB_ABBREV.findall(line)
    return len(names) >= 2


def apply_form_layout_rules(text: str) -> str:
    """Second-pass form chrome rules used after checkbox normalisation."""
    if not text:
        return text
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith(NON_EXTRACTABLE_MARKER):
            out.append(line)
            continue
        if _INSTRUCTION.search(stripped) or _ADMIN_LINE.search(stripped):
            out.append(_mark(stripped))
            continue
        if _is_empty_lab_line(stripped):
            out.append(_mark(stripped))
            continue
        yes_no = _normalise_yes_no_row(stripped)
        if yes_no is not None:
            out.append(yes_no)
            continue
        inline = _split_inline_options(stripped)
        if inline is not None:
            out.append(inline)
            continue
        out.append(line)
    return "\n".join(out)
