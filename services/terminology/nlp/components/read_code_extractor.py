"""
Extract inline Read v2/CTV3 codes embedded in GP clinical text.

Read v2 codes are 5-character alphanumeric strings starting with a letter
followed by digits/dots (e.g. ``H33..``, ``G30z.``). CTV3 codes follow a
similar pattern. This component detects them via regex and creates entities
with the label ``READ_CODE``.
"""


import re
from typing import Optional

from spacy.language import Language
from spacy.tokens import Doc, Span


_READ_V2_PATTERN = re.compile(
    r"(?<!\w)([A-Za-z]\d[\w.]{3})(?=[^\w.]|$)"
)

_CTV3_PATTERN = re.compile(
    r"(?<!\w)([A-Za-z][\w.]{4})(?=[^\w.]|$)"
)

_MINIMUM_ALPHA_RATIO = 0.2


def _looks_like_read_v2(text: str) -> bool:
    """Heuristic for Read v2: letter + digit + 3 chars, 5 total."""
    if len(text) != 5:
        return False
    if not text[0].isalpha():
        return False
    if not text[1].isdigit():
        return False
    return True


_CTV3_PARENS_PATTERN = re.compile(
    r"\(([A-Za-z][\w.]{4})\)"
)


def _looks_like_ctv3(text: str) -> bool:
    """Heuristic for CTV3: must start with X or Y (covers ~95% of CTV3 codes)."""
    if len(text) != 5:
        return False
    if text[0] not in ("X", "Y"):
        return False
    return True


@Language.factory("read_code_extractor")
class ReadCodeExtractor:
    """Extract inline Read/CTV3 codes from GP text and create entities."""

    def __init__(self, nlp: Language, name: str = "read_code_extractor"):
        self.nlp = nlp
        self.name = name

    def _extract_codes(self, doc: Doc, pattern, validator):
        """Find code matches using the given regex pattern and validator."""
        results = []
        occupied = set()
        for e in doc.ents:
            occupied.update(range(e.start, e.end))

        for match in pattern.finditer(doc.text):
            code_text = match.group(1)
            if not validator(code_text):
                continue

            char_start = match.start(1)
            char_end = match.end(1)
            span = doc.char_span(
                char_start, char_end, alignment_mode="contract"
            )
            if span is None:
                continue
            if any(i in occupied for i in range(span.start, span.end)):
                continue

            ent = Span(doc, span.start, span.end, label="READ_CODE")
            ent._.read_code = code_text.upper().rstrip(".")
            ent._.source = "read_code"
            results.append(ent)
            occupied.update(range(span.start, span.end))

        return results

    def __call__(self, doc: Doc) -> Doc:
        new_ents = self._extract_codes(doc, _READ_V2_PATTERN, _looks_like_read_v2)
        new_ents += self._extract_codes(doc, _CTV3_PARENS_PATTERN, _looks_like_ctv3)
        new_ents += self._extract_codes(doc, _CTV3_PATTERN, _looks_like_ctv3)

        if new_ents:
            seen = set()
            unique = []
            for ent in new_ents:
                key = (ent.start, ent.end)
                if key not in seen:
                    seen.add(key)
                    unique.append(ent)
            doc.ents = list(doc.ents) + unique

        return doc
