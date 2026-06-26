"""Wire-shape models shared between the rule editor, compiler, and evaluator.

Lives in libs/ so the API service, the terminology service, and any
future ingest pipeline can import the same Pydantic models without a
cross-service dependency.

Atlas trace (Phase 5 -- OBSERVATION leaf, backend):
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF

Atlas trace (Sprint 1 -- MEDICATION / ALLERGY / TREATMENT_HISTORY leaves):
    DI: DI-2199E670
    DO: DO-0EC3A9CB
"""

from libs.guidance_schema.leaf_enums import (
    AllergyStatus,
    MedicationStatus,
    TreatmentOutcome,
)
from libs.guidance_schema.medication_allergy_treatment_leaves import (
    AllergyLeaf,
    AllergyLeafValidationError,
    MedicationLeaf,
    MedicationLeafValidationError,
    TreatmentHistoryLeaf,
    TreatmentHistoryLeafValidationError,
)
from libs.guidance_schema.observation_leaf import (
    AggregationFunction,
    AggregateSpec,
    ComparisonOperator,
    DeltaKind,
    ObservationLeaf,
    ObservationLeafValidationError,
    ReferenceRangeBound,
    ReferenceRangeSpec,
    TemporalSpec,
    TrendSpec,
)

__all__ = [
    "AggregationFunction",
    "AggregateSpec",
    "AllergyLeaf",
    "AllergyLeafValidationError",
    "AllergyStatus",
    "ComparisonOperator",
    "DeltaKind",
    "MedicationLeaf",
    "MedicationLeafValidationError",
    "MedicationStatus",
    "ObservationLeaf",
    "ObservationLeafValidationError",
    "ReferenceRangeBound",
    "ReferenceRangeSpec",
    "TemporalSpec",
    "TreatmentHistoryLeaf",
    "TreatmentHistoryLeafValidationError",
    "TreatmentOutcome",
    "TrendSpec",
]
