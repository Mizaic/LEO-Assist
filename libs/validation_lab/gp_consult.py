"""Synthesise Validation Lab GP SOAP notes (separate from referral letters).

Atlas trace:
  DO: DO-E981C7B1
  DI: DI-D6E5F94E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E981C7B1")

Atlas: DI-3002D641 / DO-9F47D376
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from libs.validation_lab.models import (
    EncounterSpec,
    ObservationTrigger,
    ValidationCaseSpec,
)

# Markers that imply the GP waited for bloods before referring.
_LAB_MARKERS = (
    "psa",
    "ca125",
    "ca-125",
    "ca 125",
    "full blood count",
    "fbc",
    "haemoglobin",
    "hemoglobin",
    "iron panel",
    "ferritin",
    "transferrin",
    "lipid",
    "cholesterol",
    "hba1c",
    "hb a1c",
    "u&e",
    "u and e",
    "urea and electrolyte",
    "creatinine",
    "egfr",
    "liver function",
    "lft",
)

_LETTER_LINE = re.compile(
    r"^(dear\b|re:|yours\s+(sincerely|faithfully)|kind\s+regards|"
    r"best\s+regards|to\s+whom|please\s+find|i\s+would\s+be\s+grateful)",
    re.IGNORECASE,
)


def clinical_body_from_referral(text: str) -> str:
    """Strip letter framing so SOAP never starts with 'Dear ...'."""
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _LETTER_LINE.match(line):
            continue
        if re.match(r"^\[.+\]$", line):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body


def referral_needs_lab_wait(
    *,
    referral_text: str,
    observations: list[ObservationTrigger] | None = None,
) -> bool:
    """True when structured labs or lab keywords imply a results delay."""
    if observations:
        return True
    blob = str(referral_text or "").lower()
    return any(marker in blob for marker in _LAB_MARKERS)


def referral_delay_days(
    *,
    case_id: str,
    referral_text: str,
    observations: list[ObservationTrigger] | None = None,
) -> int:
    """Days from GP consult to referral letter.

    Obvious clinical trigger: 0-1 day.
    Waiting for bloods: 2-5 days (deterministic per case_id).
    """
    if referral_needs_lab_wait(referral_text=referral_text, observations=observations):
        digest = hashlib.sha256(str(case_id).encode("utf-8")).hexdigest()
        return 2 + (int(digest[:2], 16) % 4)
    digest = hashlib.sha256(f"fast:{case_id}".encode("utf-8")).hexdigest()
    return int(digest[:2], 16) % 2


def _pmh_terms(spec: ValidationCaseSpec) -> list[str]:
    return [
        str(item.term or item.concept_id).strip()
        for item in spec.pmh
        if item.category == "condition" and str(item.term or item.concept_id).strip()
    ]


def _observation_lines(spec: ValidationCaseSpec) -> list[str]:
    lines: list[str] = []
    for obs in spec.observations:
        label = str(obs.term or obs.observable_id).strip()
        lines.append(f"{label} {obs.value} {obs.unit}".strip())
    return lines


def _chief_complaint(clinical_body: str) -> str:
    paragraphs = [p.strip() for p in clinical_body.split("\n\n") if p.strip()]
    if paragraphs:
        return paragraphs[0][:600]
    if clinical_body:
        return clinical_body[:600]
    return "Presented with symptoms requiring specialist assessment."


def build_soap_text(spec: ValidationCaseSpec, *, referral_text: str) -> str:
    """Build a short SOAP GP note that decides referral is needed."""
    clinical = clinical_body_from_referral(referral_text)
    subjective = _chief_complaint(clinical)
    objective_bits = _observation_lines(spec)
    if not objective_bits:
        objective_bits = [
            "Observations and examination recorded in the practice system."
        ]
    conditions = _pmh_terms(spec)
    assessment = (
        "; ".join(conditions[:4])
        if conditions
        else "Working impression recorded; specialist assessment indicated."
    )
    plan = (
        "Discussed findings with the patient. Referral for specialist "
        "assessment is required. Referral letter to follow once arranged."
    )
    return (
        f"Subjective:\n{subjective}\n\n"
        f"Objective:\n" + "\n".join(f"- {bit}" for bit in objective_bits) + "\n\n"
        f"Assessment:\n{assessment}\n\n"
        f"Plan:\n{plan}"
    )


def synthesise_gp_encounter(
    spec: ValidationCaseSpec,
    *,
    referral_text: str,
    as_of: date | None = None,
) -> tuple[EncounterSpec, str]:
    """Return (GP SOAP encounter, ISO referral_date).

    GP consult is dated ``delay`` days before the referral letter date so
    Care EPR shows consult then referral, not a letter pasted into the
    consultation.
    """
    today = as_of or date.today()
    seed = referral_text or spec.referral_text or spec.reason_for_submission or ""
    delay = referral_delay_days(
        case_id=spec.case_id,
        referral_text=seed,
        observations=spec.observations,
    )
    referral_date = today
    gp_date = referral_date - timedelta(days=delay)
    text = build_soap_text(spec, referral_text=seed)
    encounter = EncounterSpec(
        label="GP consultation",
        text=text[:4000],
        date=gp_date.isoformat(),
    )
    return encounter, referral_date.isoformat()
