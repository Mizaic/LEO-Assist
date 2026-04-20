"""De-identification utilities for few-shot example serialization.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

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

_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)

_NHS_NUMBER_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")

# CTV3 / Read v2 clinical code shape: exactly 5 alphanumeric chars
# (e.g. "Ya03d", "B00zz", "X78HC"), with optional trailing dot padding.
# These collide with the compact UK postcode regex; canonical postcodes in
# clinical text always include a space ("SW1A 1AA"), so 5-char no-space tokens
# are treated as clinical codes and left intact.
_READ_CODE_SHAPE_RE = re.compile(r"^[A-Za-z0-9]{1,5}\.{0,4}$")


def _looks_like_read_code(token: str) -> bool:
    s = token.strip()
    if not s or " " in s or "\t" in s or len(s) != 5:
        return False
    return bool(_READ_CODE_SHAPE_RE.match(s))


def _replace_postcode(match: re.Match[str]) -> str:
    matched = match.group(0)
    if _looks_like_read_code(matched):
        return matched
    return "[POSTCODE]"


def deidentify_text(text: str) -> str:
    """Replace PII in text with safe placeholder tokens."""
    result = _NAME_RE.sub("[NAME]", text)
    result = _DATE_RE.sub("[DATE]", result)
    result = _NHS_NUMBER_RE.sub("[NHS_NUMBER]", result)
    result = _POSTCODE_RE.sub(_replace_postcode, result)
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
