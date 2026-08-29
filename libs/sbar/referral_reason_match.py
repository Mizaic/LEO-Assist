"""Match referral-reason headers and the taught clinical section.

Atlas:
  DI: DI-979BDE66, DI-41542A49
  DO: DO-E2BF30E7
  VT: VT-D9EC5652
"""

from __future__ import annotations

import re
from typing import Any, Sequence

_REASON_HEADER_RE = re.compile(
    r"(?:"
    r"the reason i am concerned this patient has cancer is|"
    r"the reason for referral is|"
    r"reason for referral|"
    r"reason for request|"
    r"reasons for request|"
    r"referral information|"
    r"referral criteria and clinical information|"
    r"clinical information|"
    r"i am referring this patient because|"
    r"reason i am referring"
    r")",
    re.IGNORECASE,
)
_CLINICAL_TYPES = frozenset({"free_text"})
_CLINICAL_HINTS = ("clinical", "details", "narrative", "reason")
_SKIP_TYPES = frozenset({"admin", "template_noise"})


def normalise_reason_layout(text: str) -> str:
    """Collapse table pipes and spacing so a cell still matches a header."""
    collapsed = str(text or "").replace("|", " ").replace("\t", " ")
    return " ".join(collapsed.lower().split())


def text_matches_reason_header(text: str) -> bool:
    """True when the text contains a reason header, including table cells."""
    return bool(_REASON_HEADER_RE.search(normalise_reason_layout(text)))


def extract_form_clinical_section(
    letter: str,
    sections: Sequence[Any],
) -> str | None:
    """Return the taught clinical free-text section, not admin or guidance."""
    body = str(letter or "")
    if not body or not sections:
        return None
    clinical = [_section_fields(item) for item in sections]
    clinical = [item for item in clinical if _is_clinical_section(item)]
    if not clinical:
        return None
    section = clinical[0]
    start = _find_pattern(body, section["start_pattern"])
    if start < 0:
        return None
    end = len(body)
    for other in sections:
        fields = _section_fields(other)
        if fields["section_id"] == section["section_id"]:
            continue
        pos = _find_pattern(body, fields["start_pattern"], start + 1)
        if start < pos < end:
            end = pos
    text = body[start:end].strip()
    return text or None


def _section_fields(section: Any) -> dict[str, str]:
    if isinstance(section, dict):
        return {
            "section_id": str(section.get("section_id") or ""),
            "section_type": str(section.get("section_type") or ""),
            "label": str(section.get("label") or ""),
            "start_pattern": str(section.get("start_pattern") or ""),
        }
    return {
        "section_id": str(getattr(section, "section_id", "") or ""),
        "section_type": str(getattr(section, "section_type", "") or ""),
        "label": str(getattr(section, "label", "") or ""),
        "start_pattern": str(getattr(section, "start_pattern", "") or ""),
    }


def _is_clinical_section(fields: dict[str, str]) -> bool:
    if fields["section_type"] in _SKIP_TYPES:
        return False
    if fields["section_type"] not in _CLINICAL_TYPES:
        return False
    blob = f"{fields['section_id']} {fields['label']}".lower()
    return any(hint in blob for hint in _CLINICAL_HINTS)


def _find_pattern(text: str, pattern: str, start: int = 0) -> int:
    needle = str(pattern or "").strip()
    if not needle:
        return -1
    return text.lower().find(needle.lower(), start)
