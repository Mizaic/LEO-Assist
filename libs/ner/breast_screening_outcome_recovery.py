"""Recover breast screening programme abnormal outcome as a finding."""

from __future__ import annotations

import re
from typing import Any

LABEL_FINDING = "finding"
_RECOVERY_MARKER = "_recovered_breast_screening"
# SNOMED: Breast neoplasm screening abnormal (finding); Read 68621
CONCEPT_ID = "171176006"
SNOMED_TERM = "Breast neoplasm screening abnormal (finding)"
READ_CODE = "68621"

# Block: NHS / breast screening programme then abnormal (68621), flexible whitespace.
_BREAST_SCREENING_ABNORMAL_BLOCK = re.compile(
    r"(?is)\b(?:nhs\s+)?breast\s+screening(?:\s+programme)?\b"
    r".{0,500}?"
    r"\bBreast\s+neoplasm\s+screening\s+abnormal\s*\(\s*68621\s*\)",
)
_ABNORMAL_PHRASE = re.compile(
    r"(?i)\bBreast\s+neoplasm\s+screening\s+abnormal\s*\(\s*68621\s*\)"
)
# e.g. "As per GP report list from the NHS Breast Screening Programme."
_NHS_BREAST_PREAMBLE = re.compile(
    r"(?i)as per gp report list from the nhs breast screening programme"
)


def _overlaps(
    existing: set[tuple[str, int, int]], label: str, start: int, end: int
) -> bool:
    for lab, s, e in existing:
        if lab == label and start < e and s < end:
            return True
    return False


def _existing_regions(entities: list[dict[str, Any]]) -> set[tuple[str, int, int]]:
    out: set[tuple[str, int, int]] = set()
    for ent in entities or []:
        label = str(ent.get("label") or ent.get("semantic_tag") or "").lower()
        try:
            start = int(ent.get("start", 0))
            end = int(ent.get("end", 0))
        except (TypeError, ValueError):
            continue
        out.add((label, start, end))
    return out


def _build_finding(text: str, start: int, end: int) -> dict[str, Any]:
    return {
        "text": text[start:end],
        "label": LABEL_FINDING,
        "semantic_tag": LABEL_FINDING,
        "start": start,
        "end": end,
        "assertion": "present",
        "confidence": 0.0,
        "snomed_concept_id": CONCEPT_ID,
        "snomed_term": SNOMED_TERM,
        _RECOVERY_MARKER: True,
    }


def recover_breast_screening_outcome_finding(
    text: str, entities: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Append finding for NHS breast screening abnormal (68621) if present."""
    if not text or not text.strip():
        return list(entities or [])

    current = list(entities or [])
    regions = _existing_regions(current)
    to_add: list[dict[str, Any]] = []

    for block in _BREAST_SCREENING_ABNORMAL_BLOCK.finditer(text):
        sub = _ABNORMAL_PHRASE.search(block.group(0))
        if not sub:
            continue
        start = block.start() + sub.start()
        end = block.start() + sub.end()
        if _overlaps(regions, LABEL_FINDING, start, end):
            continue
        to_add.append(_build_finding(text, start, end))
        regions.add((LABEL_FINDING, start, end))

    if not to_add:
        for ab in _ABNORMAL_PHRASE.finditer(text):
            ctx = text[max(0, ab.start() - 500) : ab.end() + 50]
            if not (
                re.search(
                    r"(?i)\b(?:nhs\s+)?breast\s+screening|breast\s+screening\s+programme\b",
                    ctx,
                )
                or _NHS_BREAST_PREAMBLE.search(ctx)
            ):
                continue
            if _overlaps(regions, LABEL_FINDING, ab.start(), ab.end()):
                continue
            to_add.append(_build_finding(text, ab.start(), ab.end()))
            regions.add((LABEL_FINDING, ab.start(), ab.end()))

    if not to_add:
        return current
    return current + to_add


__all__ = [
    "CONCEPT_ID",
    "READ_CODE",
    "SNOMED_TERM",
    "recover_breast_screening_outcome_finding",
]
