"""Unit canonicalisation for clinical observables.

Centralises the per-observable canonical-unit table and the conversion
factors so the rule editor, the compiler, the evaluator, and any
ingest pipeline all reconcile the same way (DI-<Phase 5b>).
"""

from libs.units.observable_units import (
    OBSERVABLE_UNIT_REGISTRY,
    REFERENCE_RANGES,
    UnitConversionError,
    UnknownObservableError,
    canonicalise_value,
    get_canonical_unit,
    get_reference_range,
    is_known_observable,
    list_known_observables,
)
from libs.units.unit_equivalence import normalise_unit, units_are_equivalent

__all__ = [
    "OBSERVABLE_UNIT_REGISTRY",
    "REFERENCE_RANGES",
    "UnitConversionError",
    "UnknownObservableError",
    "canonicalise_value",
    "get_canonical_unit",
    "get_reference_range",
    "is_known_observable",
    "list_known_observables",
    "normalise_unit",
    "units_are_equivalent",
]
