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
_YES_NO_DASH = re.compile(
    r"(?P<crit>(?:B\d+\.\s*)?[A-Za-z][A-Za-z0-9 /+.'-]{1,70}?)\s*[-:]\s*"
    r"Yes\s+(?P<yes>\[\s*\]|\[(?:X|x)\])\s+"
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
_CHROME_LINE = re.compile(
    r"(?i)^\s*("
    r"clinical\s+context\s*:"
    r"|current\s+repeat\s+templates\b"
    r"|clinical\s+information\s+summary\b"
    r"|nhs\s+confidential\b"
    r")"
)
_ECOG_INSTRUCTION = re.compile(
    r"(?i)No\s+ECOG\s+in\s+patient\s+record|"
    r"consider\s+using\s+tool\s+on\s+2WW[^\d[]*"
)
_SCALE_BOX = re.compile(r"(?P<grade>\d+)\s+(?P<box>\[\s*\]|\[(?:X|x)\])")


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
    match = _YES_NO.search(line) or _YES_NO_DASH.search(line)
    if not match:
        return None
    prefix = line[: match.start()].strip()
    if _is_checked(match.group("yes")):
        kept = match.group("crit").strip()
        return f"{prefix} {kept}".strip() if prefix else kept
    return prefix if prefix else _mark(match.group(0))


def _is_empty_lab_line(line: str) -> bool:
    if _HAS_DIGIT.search(line):
        return False
    names = _LAB_ABBREV.findall(line)
    return len(names) >= 2


def _is_chrome_line(line: str) -> bool:
    return bool(_CHROME_LINE.search(line))


def _split_scale_options(line: str) -> str | None:
    cleaned = _ECOG_INSTRUCTION.sub(" ", line)
    pairs = list(_SCALE_BOX.finditer(cleaned))
    if len(pairs) < 2:
        return None
    pieces: list[str] = []
    for match in pairs:
        cell = f"{match.group('grade')} {match.group('box')}"
        if _is_checked(match.group("box")):
            pieces.append(cell)
        else:
            pieces.append(_mark(cell))
    return " | ".join(pieces)


def _rewrite_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return line
    if _is_chrome_line(stripped) or _INSTRUCTION.search(stripped):
        return _mark(stripped)
    if _ADMIN_LINE.search(stripped) or _is_empty_lab_line(stripped):
        return _mark(stripped)
    yes_no = _normalise_yes_no_row(stripped)
    if yes_no is not None:
        return yes_no
    scale = _split_scale_options(stripped)
    if scale is not None:
        return scale
    inline = _split_inline_options(stripped)
    return inline if inline is not None else line


def apply_form_layout_rules(text: str) -> str:
    """Second-pass form chrome rules used after checkbox normalisation."""
    if not text:
        return text
    return "\n".join(_rewrite_line(line) for line in text.splitlines())


def llm_facing_text(text: str) -> str:
    """Drop marked chrome lines from the text shown to the extractor."""
    if not text:
        return text
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
            continue
        if "|" in line and NON_EXTRACTABLE_MARKER in line:
            cells = [
                cell.strip()
                for cell in line.split("|")
                if cell.strip() and NON_EXTRACTABLE_MARKER not in cell
            ]
            if cells:
                kept.append(" | ".join(cells))
            continue
        kept.append(line)
    return "\n".join(kept)
