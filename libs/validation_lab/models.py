"""Validation Lab domain models.

A Validation Lab case is one synthetic test patient: optional structured
past medical history (PMH), zero or more background encounters (prior
context only -- never submitted to the pipeline), and exactly one
referral document (the thing under test). This mirrors the real
production contract, where the pipeline only ever reads referral
document chunks (see docs/REFERRAL-PIPELINE-INTEGRATION.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

PmhCategory = Literal["condition", "medication", "allergy"]


class PersistMode(str, Enum):
    production = "production"
    dry_run = "dry_run"


@dataclass
class PmhItem:
    """One structured past-medical-history entry, picked via SNOMED search.

    Rendered into the referral narrative (never bypasses extraction) and
    also written as a real Condition/MedicationStatement/AllergyIntolerance
    node on the patient for display and future structured-fact use.
    """

    category: PmhCategory
    concept_id: str
    term: str = ""


@dataclass
class EncounterSpec:
    """One background encounter note -- prior context only.

    Not chunked and not submitted to the pipeline: only the referral is
    tested, matching the real production document-chunk contract.
    """

    label: str = ""
    text: str = ""
    date: str = ""


@dataclass
class ValidationCaseSpec:
    """Inputs required to create a Validation Lab test patient + graph."""

    case_id: str
    title: str
    referral_text: str
    plan_id: str = ""
    created_by: str = "validation-lab"
    patient_age: float | None = None
    patient_sex: str | None = None
    patient_name: str = ""
    pmh: list[PmhItem] = field(default_factory=list)
    encounters: list[EncounterSpec] = field(default_factory=list)
    gold: dict[str, Any] = field(default_factory=dict)
