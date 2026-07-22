"""Resolve Validation Lab patient age for scaffold and pipeline enrichment.

Age-gated NG12 compliance rules need patient_age on pipeline state.
Lab cases often mention age in referral prose without setting patient_age
explicitly (for example G5.9 wizard runs).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_AGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,3})\s*[- ]?\s*year\s*[- ]?\s*old\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*yo\b", re.IGNORECASE),
    re.compile(r"\bage\s*(?:of\s*)?(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\baged\s+(\d{1,3})\b", re.IGNORECASE),
)

_MIN_AGE = 18.0
_MAX_AGE = 100.0
_DEFAULT_AGE_SPAN = 40


def _clamp_age(raw: float) -> float:
    return max(_MIN_AGE, min(_MAX_AGE, float(raw)))


def extract_age_from_text(*texts: str) -> float | None:
    """Return the first plausible age mentioned in free text."""
    for text in texts:
        blob = str(text or "")
        if not blob.strip():
            continue
        for pattern in _AGE_PATTERNS:
            match = pattern.search(blob)
            if not match:
                continue
            try:
                age = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if _MIN_AGE <= age <= _MAX_AGE:
                return age
    return None


def default_age_from_case_id(case_id: str) -> float:
    """Deterministic adult age when nothing else is known."""
    seed = str(case_id or "validation-lab").encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    offset = int(digest[:8], 16) % _DEFAULT_AGE_SPAN
    return _clamp_age(_MIN_AGE + offset)


def resolve_patient_age(
    *,
    patient_age: float | None,
    case_id: str = "",
    referral_text: str = "",
    reason_for_submission: str = "",
    gp_encounter_text: str = "",
) -> float:
    """Choose an age for scaffold birthDate and compliance evaluation."""
    if patient_age is not None:
        return _clamp_age(patient_age)
    extracted = extract_age_from_text(
        referral_text,
        reason_for_submission,
        gp_encounter_text,
    )
    if extracted is not None:
        return extracted
    return default_age_from_case_id(case_id)


def validation_lab_age_from_case_row(row: dict[str, Any]) -> float | None:
    """Resolve age from a ValidationCase row when Patient.birthDate is absent."""
    case_id = str(row.get("case_id") or row.get("id") or "")
    gp_json = row.get("gp_encounter_json") or row.get("gp_encounter") or {}
    gp_text = ""
    if isinstance(gp_json, dict):
        gp_text = str(gp_json.get("text") or "")
    return resolve_patient_age(
        patient_age=None,
        case_id=case_id,
        referral_text=str(row.get("referral_text") or ""),
        reason_for_submission=str(row.get("reason_for_submission") or ""),
        gp_encounter_text=gp_text,
    )
