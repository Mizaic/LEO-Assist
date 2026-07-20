"""Validation Lab -- production-shaped test patients, phase runs, gold.

Atlas:
  UN: UN-4DCE95C8
  DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B
  DO: DO-3A70C3DD
"""

from libs.validation_lab.gold import (
    GoldContract,
    RunOutputs,
    promote_blocked_reason,
    score_against_gold,
)
from libs.validation_lab.models import (
    EncounterSpec,
    PersistMode,
    PmhItem,
    ValidationCaseSpec,
)
from libs.validation_lab.scaffold import SOURCE_VALIDATION_LAB, materialise_case

__all__ = [
    "EncounterSpec",
    "GoldContract",
    "PersistMode",
    "PmhItem",
    "RunOutputs",
    "SOURCE_VALIDATION_LAB",
    "ValidationCaseSpec",
    "materialise_case",
    "promote_blocked_reason",
    "score_against_gold",
]
