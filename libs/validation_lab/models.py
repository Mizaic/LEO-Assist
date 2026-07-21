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
ScenarioType = Literal["generic", "spo_ag", "ras_referral"]


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
class ObservationTrigger:
    """Numeric lab observation rendered into referral narrative for extraction.

    Also passed to GuidelineEvaluator for deterministic expectedTrigger
    stamping during brainstorm (before a case is created).
    """

    observable_id: str
    value: float
    unit: str
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
class AgConversationTurn:
    """One A&G thread message for Validation Lab scaffold."""

    category: Literal["REQUESTER", "RESPONDER"] = "REQUESTER"
    note: str = ""
    sent_datetime: str = ""
    attachment_text: str = ""


@dataclass
class ValidationCaseSpec:
    """Inputs required to create a Validation Lab test patient + graph."""

    case_id: str
    title: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    referral_text: str = ""
    case_type: Literal["referral", "ag"] = "referral"
    scenario_type: ScenarioType = "generic"
    plan_id: str = ""
    created_by: str = "validation-lab"
    patient_age: float | None = None
    patient_sex: str | None = None
    patient_name: str = ""
    nhs_number: str = ""
    gp_practice_name: str = ""
    gp_encounter: EncounterSpec | None = None
    reason_for_submission: str = ""
    verbalisation_seed: str = ""
    pmh: list[PmhItem] = field(default_factory=list)
    encounters: list[EncounterSpec] = field(default_factory=list)
    gold: dict[str, Any] = field(default_factory=dict)
    ag_thread: list[AgConversationTurn] = field(default_factory=list)
    ag_response_text: str = ""
    ag_request_attachments: list[str] = field(default_factory=list)
    ag_ubrn: str = ""
    # Synthetic-only equity fields for Validation Lab brainstorm coverage.
    # Never consumed by the rule engine.
    ethnicity_concept_id: str | None = None
    ethnicity_term: str | None = None
    performance_status_grade: int | None = None
    comorbidity_band: str | None = None
    core20_decile: int | None = None
    plus_group: str | None = None
    observations: list[ObservationTrigger] = field(default_factory=list)
