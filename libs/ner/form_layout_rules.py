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
# Most proformas print the box ahead of its Yes / No label, so the widget
# carries no criterion of its own. An optional label before it is captured so
# an untouched criterion is suppressed with the boxes.
_YES_NO_BOX_FIRST = re.compile(
    r"(?:(?P<crit>[A-Za-z][A-Za-z0-9 /+.'-]{1,70}?)\s*[-:]\s*)?"
    r"(?P<yes>\[\s*\]|\[(?:X|x)\])\s*Yes\b[\s.,:-]*"
    r"(?P<no>\[\s*\]|\[(?:X|x)\])\s*No\b",
    re.IGNORECASE,
)
_CONDITIONAL_INSTRUCTION = re.compile(r"(?i)^\s*if\s+(?:no|yes|so|not)\b")
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
    # Stop at the grade boxes without cutting a word ("F12") in half.
    r"consider\s+using\s+tool\s+on\s+2WW[^[]*?(?=\d+\s*\[)|"
    r"consider\s+using\s+tool\s+on\s+2WW[^\d[]*"
)
_TRAILING_PROSE = re.compile(
    r"(?:\[[^\]]*\]|\([^)]*\))(?![\s\S]*(?:\[[^\]]*\]|\([^)]*\)))(?P<tail>[\s\S]*)$"
)
_LEADING_BOX_LABEL = re.compile(r"(?i)^\s*(?:yes|no|x)\b[\s.:,-]*")
_SCALE_BOX = re.compile(r"(?P<grade>\d+)\s+(?P<box>\[\s*\]|\[(?:X|x)\])")
# Guidance printed on every copy of the form. It is advice to the referrer,
# never a statement about this patient. Left unmarked it becomes false facts.
_GUIDANCE_OPENER = re.compile(
    r"(?i)^\s*(?:\|\s*)?(?P<opener>"
    r"points\s+to\s+remember"
    r"|remember"
    r"|think\s+of"
    r"|do\s+not\s+(?:check|use)"
    r"|if\s+referring"
    r")\b"
)
_GUIDANCE_TOPIC = re.compile(r"(?i)cancer|risk\s+factor|guidelines?|ca\s?125|marker")
_EXTRA_SPACE = re.compile(r"[ \t]{2,}")
_PIPE_RUN = re.compile(r"(?:\|[ \t]*){2,}")


def _mark(text: str) -> str:
    stripped = text.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return text
    return f"{NON_EXTRACTABLE_MARKER} {stripped}"


def _marked_cell(text: str) -> str:
    """Fence suppressed text as its own cell so cell filters drop just it.

    Inner pipes are flattened, otherwise splitting on ``|`` would strip the
    marker off the tail of the cell and let the chrome through.
    """
    return f" | {_mark(text.replace('|', ' '))} | "


def _kept_cell(text: str) -> str:
    return f" | {text.strip()} | "


def _apply_spans(line: str, spans: list[tuple[int, int, str]]) -> str:
    """Replace spans in place, keeping every character outside them.

    Rewriting a form line must never shorten it. On this proforma the GP
    narrative shares a line with the checkboxes, so rebuilding the line from
    the boxes alone silently deletes the referral reason.
    """
    out: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        if start < cursor:
            continue
        out.append(line[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(line[cursor:])
    joined = _PIPE_RUN.sub("| ", _EXTRA_SPACE.sub(" ", "".join(out)))
    return joined.strip()


def _is_checked(box: str) -> bool:
    return bool(_CHECKED.search(box)) and not (
        _UNCHECKED.search(box) and not _CHECKED.search(box)
    )


def _split_inline_options(line: str) -> str | None:
    pairs = list(_INLINE_PAIR.finditer(line))
    if len(pairs) < 2:
        return None
    spans: list[tuple[int, int, str]] = []
    for match in pairs:
        cell = match.group(0)
        spans.append(
            (
                match.start(),
                match.end(),
                (
                    _kept_cell(cell)
                    if _is_checked(match.group("box"))
                    else _marked_cell(cell)
                ),
            )
        )
    return _apply_spans(line, spans)


def _normalise_yes_no_row(line: str) -> str | None:
    match = _YES_NO.search(line) or _YES_NO_DASH.search(line)
    if not match:
        return None
    if not _is_checked(match.group("yes")):
        return _apply_spans(
            line, [(match.start(), match.end(), _marked_cell(match.group(0)))]
        )
    # Ticked: assert the criterion, suppress the box row that carries it.
    crit_end = match.end("crit")
    replacement = _kept_cell(match.group("crit")) + _marked_cell(
        line[crit_end : match.end()]
    )
    return _apply_spans(line, [(match.start(), match.end(), replacement)])


def _normalise_box_first_yes_no(line: str) -> str | None:
    """Fence an untouched box-first Yes / No widget, keeping text beside it.

    Nothing ticked means the widget says nothing about this patient, but the
    free text sharing the cell may be the referral reason. Suppressing the
    whole cell would delete it, so only the widget is marked.
    """
    match = _YES_NO_BOX_FIRST.search(line)
    if match is None:
        return None
    if _is_checked(match.group("yes")) or _is_checked(match.group("no")):
        return None
    spans = [(match.start(), match.end(), _marked_cell(match.group(0)))]
    tail = line[match.end() :]
    if _CONDITIONAL_INSTRUCTION.search(tail.strip(" |\t")):
        spans.append((match.end(), len(line), _marked_cell(tail)))
    return _apply_spans(line, spans)


def _is_empty_lab_line(line: str) -> bool:
    if _HAS_DIGIT.search(line):
        return False
    names = _LAB_ABBREV.findall(line)
    return len(names) >= 2


def _is_chrome_line(line: str) -> bool:
    return bool(_CHROME_LINE.search(line))


def has_trailing_prose(cell: str, *, min_words: int = 4) -> bool:
    """True when free text follows the last checkbox in *cell*.

    A form criterion puts its box at the end of the cell. This proforma packs
    the GP narrative after the box on the same line, so a cell with text after
    the last box must never be suppressed as a whole.
    """
    match = _TRAILING_PROSE.search(cell)
    if not match:
        return False
    tail = _LEADING_BOX_LABEL.sub("", match.group("tail")).strip(" |\t")
    return len(tail.split()) >= min_words


def _is_guidance_line(line: str) -> bool:
    """True for referrer advice printed on the form, not a patient statement.

    "Remember" needs a guidance topic alongside it, so a GP writing
    "Remember she is on HRT" is still read as clinical text.
    """
    match = _GUIDANCE_OPENER.search(line)
    if not match:
        return False
    if match.group("opener").lower().startswith("points to remember"):
        return True
    return bool(_GUIDANCE_TOPIC.search(line))


def _split_scale_options(line: str) -> str | None:
    instructions = list(_ECOG_INSTRUCTION.finditer(line))
    pairs = [
        match
        for match in _SCALE_BOX.finditer(line)
        if not any(i.start() <= match.start() < i.end() for i in instructions)
    ]
    if len(pairs) < 2:
        return None
    spans = [(i.start(), i.end(), _marked_cell(i.group(0))) for i in instructions]
    for match in pairs:
        cell = match.group(0)
        spans.append(
            (
                match.start(),
                match.end(),
                (
                    _kept_cell(cell)
                    if _is_checked(match.group("box"))
                    else _marked_cell(cell)
                ),
            )
        )
    spans.sort(key=lambda span: span[0])
    return _apply_spans(line, spans)


def _rewrite_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith(NON_EXTRACTABLE_MARKER):
        return line
    if (
        _is_chrome_line(stripped)
        or _is_guidance_line(stripped)
        or _INSTRUCTION.search(stripped)
    ):
        return _mark(stripped)
    if _ADMIN_LINE.search(stripped) or _is_empty_lab_line(stripped):
        return _mark(stripped)
    yes_no = _normalise_yes_no_row(stripped)
    if yes_no is not None:
        return yes_no
    box_first = _normalise_box_first_yes_no(stripped)
    if box_first is not None:
        return box_first
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
