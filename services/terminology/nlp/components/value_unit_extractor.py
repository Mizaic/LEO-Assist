"""
Extract clinical measurements from GP encounter text.

Detects blood pressure, BMI, lab values, temperature, weight, and height
using regex patterns. Creates entities with label ``MEASUREMENT`` and sets
``Span._.value``, ``Span._.unit``, ``Span._.measurement_type``.
"""

import re

from spacy.language import Language
from spacy.tokens import Doc, Span

_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "blood_pressure",
        re.compile(
            r"(?:(?:BP|bp|blood\s*pressure)\s*[:=]?\s*)"
            r"(\d{2,3})\s*/\s*(\d{2,3})"
            r"(?:\s*(?:mmHg|mmhg))?"
        ),
        "mmHg",
    ),
    (
        "bmi",
        re.compile(
            r"(?:BMI|bmi)\s*[:=]?\s*(\d{1,2}(?:\.\d{1,2})?)"
            r"(?:\s*(?:kg/m2|kg/m²))?"
        ),
        "kg/m2",
    ),
    (
        "temperature",
        re.compile(
            r"(?:temp|temperature|T)\s*[:=]?\s*"
            r"(\d{2}(?:\.\d{1,2})?)\s*(?:°?[CcFf]|degrees?)?"
        ),
        "°C",
    ),
    (
        "weight",
        re.compile(
            r"(?:weight|wt|Wt)\s*[:=]?\s*"
            r"(\d{2,3}(?:\.\d{1,2})?)\s*(?:kg|Kg|KG|st|lbs?)?"
        ),
        "kg",
    ),
    (
        "height",
        re.compile(
            r"(?:height|ht|Ht)\s*[:=]?\s*"
            r"(\d{1,3}(?:\.\d{1,2})?)\s*(?:cm|m|CM|M)?"
        ),
        "cm",
    ),
    (
        "heart_rate",
        re.compile(
            r"(?:(?<!\w)HR|(?<!\w)hr|pulse|heart\s*rate|(?<![A-Za-z])P(?=\s*[:=]))"
            r"\s*[:=]?\s*(\d{2,3})\s*(?:bpm|/min)?"
        ),
        "bpm",
    ),
    (
        "respiratory_rate",
        re.compile(
            r"(?:RR|rr|resp\s*rate)\s*[:=]?\s*"
            r"(\d{1,2})\s*(?:/min|breaths)?"
        ),
        "/min",
    ),
    (
        "oxygen_saturation",
        re.compile(
            r"(?:SpO2|spo2|sats?|O2\s*sats?)\s*[:=]?\s*"
            r"(\d{2,3})\s*%?"
        ),
        "%",
    ),
    (
        "hba1c",
        re.compile(
            r"(?:HbA1c|hba1c|HbA1C)\s*[:=]?\s*"
            r"(\d{2,3}(?:\.\d)?)\s*(?:mmol/mol|%)?"
        ),
        "mmol/mol",
    ),
    (
        "egfr",
        re.compile(
            r"(?:eGFR|egfr|GFR|gfr)\s*[:=]?\s*"
            r"(\d{1,3}(?:\.\d)?)"
        ),
        "mL/min/1.73m2",
    ),
    (
        "creatinine",
        re.compile(
            r"(?:creatinine|creat)\s*[:=]?\s*"
            r"(\d{2,4})\s*(?:umol/L|µmol/L)?"
        ),
        "µmol/L",
    ),
    (
        "haemoglobin",
        re.compile(
            r"(?:Hb|hb|haemoglobin|hemoglobin)\s*[:=]?\s*"
            r"(\d{2,3}(?:\.\d)?)\s*(?:g/L|g/dL|g/l)?"
        ),
        "g/L",
    ),
]


@Language.factory("value_unit_extractor")
class ValueUnitExtractor:
    """Extract clinical measurements from text."""

    def __init__(self, nlp: Language, name: str = "value_unit_extractor"):
        self.nlp = nlp
        self.name = name

    def __call__(self, doc: Doc) -> Doc:
        new_ents: list[Span] = []
        occupied = set()
        for e in doc.ents:
            occupied.update(range(e.start, e.end))

        for mtype, pattern, default_unit in _PATTERNS:
            for match in pattern.finditer(doc.text):
                if mtype == "blood_pressure":
                    value = f"{match.group(1)}/{match.group(2)}"
                else:
                    value = match.group(1)

                char_start, char_end = match.span()
                span = doc.char_span(
                    char_start, char_end, alignment_mode="expand"
                )
                if span is None:
                    continue
                if any(i in occupied for i in range(span.start, span.end)):
                    continue

                ent = Span(doc, span.start, span.end, label="MEASUREMENT")
                ent._.value = value
                ent._.unit = default_unit
                ent._.measurement_type = mtype
                new_ents.append(ent)
                occupied.update(range(span.start, span.end))

        if new_ents:
            doc.ents = list(doc.ents) + new_ents

        return doc
