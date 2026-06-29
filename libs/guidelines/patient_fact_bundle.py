"""Shared in-memory patient fact bundle for guideline evaluation.

Atlas trace:
  DO: DO-20B3BDD7
  DI: DI-2687230E

This module defines the single data shape passed to the GuidelineEvaluator,
the SBAR formatter, and test replay. The evaluator must not query Neo4j
directly; all patient facts travel through this bundle.

Fail-closed contract:
  - When a fact list is not available, pass an empty list.
  - The evaluator treats an empty list as "no data" and fails closed.
  - Facts with unknown status are stored unchanged and will fail closed in
    the evaluator because MedicationStatus.unknown / AllergyStatus.unknown /
    TreatmentOutcome.unknown are all non-matching values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class MedicationFact:
    """One medication entry in the patient's current or recent drug list.

    Fields
    ------
    drug_class : str
        Drug class label used for matching (e.g. "NSAID", "PPI", "H2RA").
        Must match the drug_class field on the MEDICATION leaf.
    status : str
        MedicationStatus enum value as a string.
        Only "active" passes a MEDICATION leaf; all others fail closed.
    source_ids : list[str]
        Source encounter or document identifiers for audit and SBAR citation.
    concept_id : str | None
        Optional SNOMED or dm+d concept identifier for exact-code matching.
    term : str
        Plain-English drug name or preferred term (for diagnostics display).
    recorded_date : date | None
        Date the medication was last documented as active.
    """

    drug_class: str
    status: str
    source_ids: list[str] = field(default_factory=list)
    concept_id: str | None = None
    term: str = ""
    recorded_date: date | None = None


@dataclass
class AllergyFact:
    """One allergy entry for the patient.

    Fields
    ------
    substance_concept_id : str
        SNOMED concept ID of the allergen (e.g. penicillin concept).
    status : str
        AllergyStatus enum value as a string.
        Only "active" passes an ALLERGY leaf.
        "nkda" and "unknown" both fail closed but produce different reasons.
    source_ids : list[str]
        Source encounter or document identifiers.
    allergy_class : str | None
        Optional class label for class-level allergy rules (e.g. "penicillin").
    term : str
        Plain-English allergen name (for diagnostics display).
    """

    substance_concept_id: str
    status: str
    source_ids: list[str] = field(default_factory=list)
    allergy_class: str | None = None
    term: str = ""


@dataclass
class TreatmentFact:
    """One treatment history event for the patient.

    Fields
    ------
    treatment_class : str
        Treatment class label used for matching (e.g. "PPI", "H2RA").
    outcome : str
        TreatmentOutcome enum value as a string.
        Only "failed" and "not_tolerated" pass a TREATMENT_HISTORY leaf.
    source_ids : list[str]
        Source encounter or document identifiers.
    concept_id : str | None
        Optional SNOMED or dm+d concept identifier.
    term : str
        Plain-English treatment name (for diagnostics display).
    duration_days : int | None
        Duration of the treatment in days (if recorded).
        Used for min_duration_days checks on TREATMENT_HISTORY leaves.
    start_date : date | None
        Date treatment was started.
    end_date : date | None
        Date treatment was stopped or completed.
    """

    treatment_class: str
    outcome: str
    source_ids: list[str] = field(default_factory=list)
    concept_id: str | None = None
    term: str = ""
    duration_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass
class GuidelinePatientFactBundle:
    """All patient facts needed for guideline evaluation.

    This bundle is the single input to GuidelineEvaluator.evaluate_patient()
    for the new MEDICATION, ALLERGY, and TREATMENT_HISTORY leaf kinds.
    It also carries the existing fields (patient_codes, patient_observations)
    so everything travels together.

    The evaluator, SBAR formatter, and test replay all receive the same
    bundle shape. This prevents drift between the evaluation result and
    the explanation shown to reviewers.

    Usage
    -----
    For test replay and Sprint 1 unit tests, build the bundle directly from
    synthetic fixtures. For live pipeline evaluation, the compliance subgraph
    builds the bundle from workflow state and passes it through.

    Fail-closed: pass empty lists when data is not available. Do not omit
    the field or pass None -- use [] instead.
    """

    patient_codes: list[str] = field(default_factory=list)
    patient_observations: list[dict[str, Any]] = field(default_factory=list)
    active_medications: list[MedicationFact] = field(default_factory=list)
    allergies: list[AllergyFact] = field(default_factory=list)
    treatment_history: list[TreatmentFact] = field(default_factory=list)
    as_of_date: date | None = None


def empty_bundle() -> GuidelinePatientFactBundle:
    """Return a bundle with all lists empty and no as_of_date.

    Use as a safe default when no patient facts are available. The
    evaluator will fail closed for all MEDICATION, ALLERGY, and
    TREATMENT_HISTORY leaves when the lists are empty.
    """
    return GuidelinePatientFactBundle()
