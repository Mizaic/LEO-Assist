"""Training data promotion utilities (Atlas DI-C424BB44).

This package wires manual reviewer reconciliation events into the
:GoldLabel / :TrainingCandidate corpora used by the model retraining
pipelines. See ``reconcile_promoter`` for the entry point.
"""

from libs.training_data.reconcile_promoter import (
    EncounterContext,
    promote_lock_to_gold,
)

__all__ = [
    "EncounterContext",
    "promote_lock_to_gold",
]
