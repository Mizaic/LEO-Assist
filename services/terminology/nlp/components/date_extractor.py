"""
Extract dates and temporal references from UK GP clinical text.

Handles UK date formats (dd/mm/yyyy), month-name dates, relative temporal
references ("3 weeks ago", "last month"), and durations ("for 2 weeks",
"since June"). Creates entities with label ``DATE`` and sets
``Span._.date_value`` and ``Span._.temporal_type``.
"""


import re

from spacy.language import Language
from spacy.tokens import Doc, Span

_UK_DATE = re.compile(
    r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b"
)

_MONTH_DATE = re.compile(
    r"\b(\d{1,2})?\s*"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
    r"\s*(\d{2,4})?\b",
    re.IGNORECASE,
)

_RELATIVE = re.compile(
    r"\b(\d{1,3})\s+"
    r"(day|days|week|weeks|month|months|year|years)\s+"
    r"(ago|previously|earlier|before)\b",
    re.IGNORECASE,
)

_RELATIVE_WORD = re.compile(
    r"\b(yesterday|today|last\s+(?:week|month|year)|"
    r"this\s+(?:week|month|year)|recently|recent)\b",
    re.IGNORECASE,
)

_DURATION = re.compile(
    r"\b(for|since|over|past)\s+"
    r"(?:the\s+)?(?:last\s+)?"
    r"(\d{1,3})?\s*"
    r"(day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE,
)


@Language.factory("date_extractor")
class DateExtractor:
    """Extract dates and temporal references from clinical text."""

    def __init__(self, nlp: Language, name: str = "date_extractor"):
        self.nlp = nlp
        self.name = name

    def __call__(self, doc: Doc) -> Doc:
        new_ents: list[Span] = []
        existing_spans = {(e.start, e.end) for e in doc.ents}

        for pattern, temporal_type in [
            (_UK_DATE, "absolute"),
            (_MONTH_DATE, "absolute"),
            (_RELATIVE, "relative"),
            (_RELATIVE_WORD, "relative"),
            (_DURATION, "duration"),
        ]:
            for match in pattern.finditer(doc.text):
                char_start, char_end = match.span()
                span = doc.char_span(
                    char_start, char_end, alignment_mode="contract"
                )
                if span is None or len(span) == 0:
                    continue
                if (span.start, span.end) in existing_spans:
                    continue

                ent = Span(doc, span.start, span.end, label="DATE")
                ent._.date_value = match.group(0).strip()
                ent._.temporal_type = temporal_type
                new_ents.append(ent)
                existing_spans.add((span.start, span.end))

        if new_ents:
            try:
                doc.ents = list(doc.ents) + new_ents
            except ValueError:
                pass

        return doc
