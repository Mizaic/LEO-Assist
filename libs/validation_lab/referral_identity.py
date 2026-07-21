"""Fill identity placeholders in Validation Lab referral letters.

Atlas: DI-3002D641 / DO-9F47D376
"""

from __future__ import annotations

import re

_TOKEN_MAP: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[Patient Name\]", re.IGNORECASE), "patient_name"),
    (re.compile(r"\[Patient's Name\]", re.IGNORECASE), "patient_name"),
    (re.compile(r"\[Name\]", re.IGNORECASE), "patient_name"),
    (re.compile(r"\[DOB\]", re.IGNORECASE), "birth_date"),
    (re.compile(r"\[Date of Birth\]", re.IGNORECASE), "birth_date"),
    (re.compile(r"\[GP Name\]", re.IGNORECASE), "gp_name"),
    (re.compile(r"\[GP Practice\]", re.IGNORECASE), "gp_name"),
    (re.compile(r"\[Practice Name\]", re.IGNORECASE), "gp_name"),
)


def fill_referral_identity(
    text: str,
    *,
    patient_name: str = "",
    birth_date: str = "",
    gp_name: str = "",
) -> str:
    """Replace common bracket identity tokens; leave unknown tokens alone."""
    out = str(text or "")
    values = {
        "patient_name": str(patient_name or "").strip(),
        "birth_date": str(birth_date or "").strip(),
        "gp_name": str(gp_name or "").strip(),
    }
    for pattern, key in _TOKEN_MAP:
        replacement = values.get(key) or ""
        if not replacement:
            continue
        out = pattern.sub(replacement, out)
    return out
