"""Pydantic wire shapes for MEDICATION, ALLERGY, and TREATMENT_HISTORY leaves.

Atlas trace:
  DO: DO-0EC3A9CB
  DI: DI-2199E670

These models define the rule-authoring payload for the three new leaf kinds.
They describe the QUESTION a rule asks (e.g. "is the patient on an NSAID?"),
not the patient's actual facts. Patient facts travel in GuidelinePatientFactBundle.

Pattern mirrors libs.guidance_schema.observation_leaf -- extra="forbid" on
every model so unexpected fields from the LLM are rejected at compile time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from libs.guidance_schema.leaf_enums import (
    AllergyStatus,
    MedicationStatus,
    TreatmentOutcome,
)


class MedicationLeafValidationError(ValueError):
    """Raised when a MEDICATION leaf payload is structurally invalid."""


class AllergyLeafValidationError(ValueError):
    """Raised when an ALLERGY leaf payload is structurally invalid."""


class TreatmentHistoryLeafValidationError(ValueError):
    """Raised when a TREATMENT_HISTORY leaf payload is structurally invalid."""


class MedicationLeaf(BaseModel):
    """Rule leaf: 'Is the patient currently on a medication of this class?'

    Evaluation:
      - Matches when the patient has at least one MedicationFact whose
        drug_class equals this leaf's drug_class AND whose status is
        MedicationStatus.active.
      - If concept_id is also set, the patient fact must match that code too.
      - All other statuses (stopped, planned, historical, unknown) fail closed.
      - An empty active_medications list fails closed.
    """

    model_config = {"extra": "forbid"}

    kind: Literal["MEDICATION"] = Field(
        default="MEDICATION",
        description="Discriminator. Always MEDICATION.",
    )
    node_id: str | None = Field(
        default=None,
        description="Stable client-side id for tree mutations.",
    )
    drug_class: str = Field(
        min_length=1,
        description=(
            "Drug class to match against (e.g. 'NSAID', 'PPI', 'H2RA'). "
            "Must match the drug_class on the patient's MedicationFact."
        ),
    )
    concept_id: str | None = Field(
        default=None,
        description=(
            "Optional SNOMED or dm+d concept ID for exact-code matching. "
            "When set, the patient fact must match both drug_class and concept_id."
        ),
    )
    term: str = Field(
        default="",
        description="Human-readable drug name for display in the rule editor.",
    )

    @model_validator(mode="after")
    def _require_drug_class(self) -> "MedicationLeaf":
        if not self.drug_class:
            raise MedicationLeafValidationError(
                "MEDICATION leaf requires a non-empty drug_class."
            )
        return self


class AllergyLeaf(BaseModel):
    """Rule leaf: 'Does the patient have an active allergy to this substance?'

    Evaluation:
      - Matches when the patient has at least one AllergyFact whose
        substance_concept_id equals this leaf's substance_concept_id AND
        whose status is AllergyStatus.active.
      - If allergy_class is set, also matches a fact whose allergy_class
        equals this leaf's allergy_class (class-level match).
      - nkda status: does NOT match; reason = "documented no known drug allergies".
      - unknown status or empty list: fails closed; reason = "fail closed".
    """

    model_config = {"extra": "forbid"}

    kind: Literal["ALLERGY"] = Field(
        default="ALLERGY",
        description="Discriminator. Always ALLERGY.",
    )
    node_id: str | None = Field(
        default=None,
        description="Stable client-side id for tree mutations.",
    )
    substance_concept_id: str = Field(
        min_length=1,
        description=(
            "SNOMED concept ID of the allergen the rule is asking about. "
            "Must match the substance_concept_id on the patient's AllergyFact."
        ),
    )
    allergy_class: str | None = Field(
        default=None,
        description=(
            "Optional class-level match label (e.g. 'penicillin'). "
            "When set, a patient fact whose allergy_class matches also passes."
        ),
    )
    term: str = Field(
        default="",
        description="Human-readable allergen name for display.",
    )

    @model_validator(mode="after")
    def _require_substance_concept_id(self) -> "AllergyLeaf":
        if not self.substance_concept_id:
            raise AllergyLeafValidationError(
                "ALLERGY leaf requires a non-empty substance_concept_id."
            )
        return self


class TreatmentHistoryLeaf(BaseModel):
    """Rule leaf: 'Has the patient tried and failed this treatment?'

    Evaluation:
      - Matches when the patient has at least one TreatmentFact whose
        treatment_class equals this leaf's treatment_class AND whose outcome
        is TreatmentOutcome.failed or TreatmentOutcome.not_tolerated.
      - If min_duration_days is set, the fact's duration_days must be
        >= min_duration_days. A fact with no duration_days recorded fails
        closed when min_duration_days is required.
      - If concept_id is also set, the fact must match that code too.
      - All other outcomes (ongoing, planned, completed, unknown) fail closed.
      - An empty treatment_history list fails closed.
    """

    model_config = {"extra": "forbid"}

    kind: Literal["TREATMENT_HISTORY"] = Field(
        default="TREATMENT_HISTORY",
        description="Discriminator. Always TREATMENT_HISTORY.",
    )
    node_id: str | None = Field(
        default=None,
        description="Stable client-side id for tree mutations.",
    )
    treatment_class: str = Field(
        min_length=1,
        description=(
            "Treatment class to match against (e.g. 'PPI', 'H2RA'). "
            "Must match the treatment_class on the patient's TreatmentFact."
        ),
    )
    concept_id: str | None = Field(
        default=None,
        description=(
            "Optional SNOMED or dm+d concept ID for exact-code matching."
        ),
    )
    min_duration_days: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Minimum treatment duration in days required for a match. "
            "When set, a fact whose duration_days is absent or shorter fails closed."
        ),
    )
    term: str = Field(
        default="",
        description="Human-readable treatment name for display.",
    )

    @model_validator(mode="after")
    def _require_treatment_class(self) -> "TreatmentHistoryLeaf":
        if not self.treatment_class:
            raise TreatmentHistoryLeafValidationError(
                "TREATMENT_HISTORY leaf requires a non-empty treatment_class."
            )
        return self


__all__ = [
    "AllergyLeaf",
    "AllergyLeafValidationError",
    "MedicationLeaf",
    "MedicationLeafValidationError",
    "TreatmentHistoryLeaf",
    "TreatmentHistoryLeafValidationError",
    "MedicationStatus",
    "AllergyStatus",
    "TreatmentOutcome",
]
