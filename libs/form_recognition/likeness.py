"""Is this document laid out like a form or written like a letter?

This only decides between "untaught form" (pause for a person) and
"plain letter" (carry on with the generic path). When the signals are
mixed the answer is "unsure", and unsure is treated as a form, so a
doubtful document always reaches a person.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from libs.form_recognition.normalise import BOX_TOKEN, normalise_text, segments

Band = Literal["form", "letter", "unsure"]

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_LABEL_LINE_RE = re.compile(r"^[^.!?]{2,60}:\s*(?:\||$)")
_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s|\**\s*section\s+[a-z0-9]{1,3}\b)", re.I)
_INSTRUCTION_RE = re.compile(
    r"please\s+(?:tick|put\s+an?\s+x|mark|complete\s+all)|tick\s+(?:as\s+)?"
    r"appropriate|tick\s+(?:all|one|the\s+box)|delete\s+as\s+appropriate",
    re.IGNORECASE,
)
_SALUTATION_RE = re.compile(r"^\s*\**\s*dear\b", re.IGNORECASE | re.MULTILINE)
_SIGN_OFF_RE = re.compile(
    r"yours\s+(?:sincerely|faithfully)|kind\s+regards|best\s+wishes|many\s+thanks",
    re.IGNORECASE,
)
_EMAIL_HEADER_RE = re.compile(r"^\s*(?:from|to|subject|sent|cc):\s*\S", re.I | re.M)
_PROSE_MIN_WORDS = 20
_PROSE_MIN_LINES = 2


@dataclass(frozen=True)
class Likeness:
    """The layout band and the points that led to it."""

    band: Band
    form_points: int
    letter_points: int
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def form_like(self) -> bool:
        return self.band != "letter"

    def to_dict(self) -> dict[str, object]:
        return {
            "band": self.band,
            "form_points": self.form_points,
            "letter_points": self.letter_points,
            "signals": list(self.signals),
        }


def _count(lines: list[str], pattern: re.Pattern[str]) -> int:
    return sum(1 for line in lines if pattern.search(line))


def _form_signals(text: str, lines: list[str]) -> list[tuple[str, int]]:
    boxes = normalise_text(text).split().count(BOX_TOKEN)
    rows = _count(lines, _TABLE_ROW_RE)
    labels = sum(1 for s in segments(text) if _LABEL_LINE_RE.match(s.raw.strip("* ")))
    headings = _count(lines, _HEADING_RE)
    signals = [
        ("tick_boxes", 2 if boxes >= 3 else 0),
        ("table_rows", 1 if rows >= 5 else 0),
        ("field_labels", 1 if labels >= 5 else 0),
        ("section_headings", 2 if headings >= 2 else 0),
        ("form_instructions", 1 if _INSTRUCTION_RE.search(text) else 0),
    ]
    return [s for s in signals if s[1]]


def _letter_signals(text: str, lines: list[str]) -> list[tuple[str, int]]:
    prose = sum(
        1 for line in lines if "|" not in line and len(line.split()) >= _PROSE_MIN_WORDS
    )
    email_headers = len(_EMAIL_HEADER_RE.findall(text))
    signals = [
        ("salutation", 2 if _SALUTATION_RE.search(text) else 0),
        ("sign_off", 2 if _SIGN_OFF_RE.search(text) else 0),
        ("email_headers", 2 if email_headers >= 2 else 0),
        ("prose_paragraphs", 1 if prose >= _PROSE_MIN_LINES else 0),
    ]
    return [s for s in signals if s[1]]


def _band(form: list[tuple[str, int]], letter_points: int) -> Band:
    form_points = sum(points for _, points in form)
    has_boxes = any(name == "tick_boxes" for name, _ in form)
    if letter_points >= 3 and not has_boxes:
        return "letter"
    if letter_points >= 2 and form_points <= 1:
        return "letter"
    if form_points >= 3:
        return "form"
    return "unsure"


def assess_likeness(text: str) -> Likeness:
    """Score how form-like *text* is. Unsure means treat it as a form."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    form = _form_signals(text or "", lines)
    letter = _letter_signals(text or "", lines)
    form_points = sum(points for _, points in form)
    letter_points = sum(points for _, points in letter)
    names = tuple(name for name, _ in form + letter)
    return Likeness(_band(form, letter_points), form_points, letter_points, names)
