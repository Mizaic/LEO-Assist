"""Text normalisation shared by every form-recognition score.

Ticked and blank boxes, table pipes, markdown marks, digits and case all
vary between converters and between filled-in copies of the same form.
None of them says which form a document is, so they are folded away
before any comparison.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

BOX_TOKEN = "qbox"

_BOX_RE = re.compile(r"\[\s*(?:x|\*|yes)?\s*\]|[\u2610\u2611\u2612]", re.IGNORECASE)
_NON_LETTER_RE = re.compile(r"[\W\d_]+")
_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$")
_MARKUP_RE = re.compile(r"[*_`]+")
_SECTION_RE = re.compile(r"^section\s+[a-z0-9]{1,3}\b", re.IGNORECASE)
_MAX_HEADING_WORDS = 15
_ANSWER_WORDS = frozenset({"yes", "no", "none", "other", "unknown", "page", "n", "a"})


@dataclass(frozen=True)
class Segment:
    """One cell or line of a document, raw and normalised."""

    raw: str
    norm: str
    markdown_heading: bool = False

    @property
    def has_box(self) -> bool:
        return BOX_TOKEN in self.norm.split()

    @property
    def words(self) -> str:
        """The normalised text with box tokens removed."""
        return " ".join(w for w in self.norm.split() if w != BOX_TOKEN)

    def _meaningful(self) -> bool:
        words = self.words.split()
        if not words or len(words) > _MAX_HEADING_WORDS:
            return False
        if all(w in _ANSWER_WORDS for w in words):
            return False
        return len(self.words) >= 4 and any(len(w) >= 3 for w in words)

    def is_clinical_structure(self) -> bool:
        """True for a section heading or a tick-box option.

        Field labels such as "Surname:" are on every referral form and in
        no taught schema, so they say nothing about which form this is.
        """
        if not self._meaningful():
            return False
        if self.has_box or self.markdown_heading:
            return True
        return bool(_SECTION_RE.match(_MARKUP_RE.sub("", self.raw).strip()))


def split_at_first_box(text: str) -> tuple[str, str]:
    """Return the text before and after the first tick box in *text*."""
    match = _BOX_RE.search(text or "")
    if match is None:
        return text or "", ""
    return text[: match.start()], text[match.end() :]


def normalise_text(text: str) -> str:
    """Fold *text* to lower-case words, with every tick box as BOX_TOKEN."""
    folded = unicodedata.normalize("NFKC", text or "")
    folded = _BOX_RE.sub(f" {BOX_TOKEN} ", folded)
    folded = folded.casefold()
    return " ".join(_NON_LETTER_RE.sub(" ", folded).split())


def _is_separator(line: str) -> bool:
    return bool(_SEPARATOR_RE.match(line.strip()))


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return [stripped]
    return [c.strip() for c in stripped.strip("|").split("|")]


def segments(text: str) -> list[Segment]:
    """Split *text* into non-empty cells and lines, in document order."""
    found: list[Segment] = []
    for line in (text or "").splitlines():
        if not line.strip() or _is_separator(line):
            continue
        heading = line.lstrip().startswith("#")
        for cell in _cells(line):
            norm = normalise_text(cell)
            if norm:
                found.append(Segment(cell, norm, heading))
    return found


def outline(text: str) -> list[str]:
    """Return the normalised non-empty cells and lines of *text*."""
    return [segment.norm for segment in segments(text)]
