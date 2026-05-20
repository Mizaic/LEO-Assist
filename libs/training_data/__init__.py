"""Training data promotion utilities (Atlas DI-C424BB44).

This package wires manual reviewer reconciliation events into the
:GoldLabel / :TrainingCandidate corpora used by the model retraining
pipelines. See ``reconcile_promoter`` for the entry point.
"""

__all__ = [
    "EncounterContext",
    "promote_lock_to_gold",
]


def __getattr__(name: str):
    if name in __all__:
        from libs.training_data.reconcile_promoter import (
            EncounterContext,
            promote_lock_to_gold,
        )

        return {
            "EncounterContext": EncounterContext,
            "promote_lock_to_gold": promote_lock_to_gold,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
