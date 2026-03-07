"""De-identification utilities for few-shot example serialization.

Replaces PII (names, dates, values, units, findings, locations) with
safe placeholder tokens so that few-shot examples do not poison prompts.
"""

from __future__ import annotations

import re
from typing import Any

_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
)

_DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"\s+\d{2,4}\b",
    re.IGNORECASE,
)

_NUMERIC_VALUE_RE = re.compile(
    r"\b\d+\.?\d*\s*(?:mg|mcg|ml|mmol|umol|g|kg|L|dL|mmHg|bpm|%|IU)\b",
    re.IGNORECASE,
)

_POSTCODE_RE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE
)

_NHS_NUMBER_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")


def deidentify_text(text: str) -> str:
    """Replace PII in text with safe placeholder tokens."""
    result = _NAME_RE.sub("[NAME]", text)
    result = _DATE_RE.sub("[DATE]", result)
    result = _NHS_NUMBER_RE.sub("[NHS_NUMBER]", result)
    result = _POSTCODE_RE.sub("[POSTCODE]", result)
    result = _NUMERIC_VALUE_RE.sub("[VALUE]", result)
    return result


def deidentify_example(example: dict[str, Any]) -> dict[str, Any]:
    """De-identify a few-shot example dict for safe prompt inclusion.

    Expects keys like ``encounter_text``, ``entities``, etc.
    """
    result = dict(example)

    if "encounter_text" in result:
        result["encounter_text"] = deidentify_text(result["encounter_text"])

    if "entities" in result and isinstance(result["entities"], list):
        cleaned_entities = []
        for entity in result["entities"]:
            cleaned = dict(entity)
            if "text" in cleaned:
                cleaned["text"] = deidentify_text(cleaned["text"])
            if "normalized" in cleaned:
                cleaned["normalized"] = deidentify_text(cleaned["normalized"])
            cleaned_entities.append(cleaned)
        result["entities"] = cleaned_entities

    return result
