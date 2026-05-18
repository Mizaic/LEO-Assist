"""Active-learning loop for the v2 episode detector.

Phase 5 of the episode-first rebuild. Closes the feedback loop from
manual reviewer corrections back into the detector's per-site
evidence-aggregator weights.

Atlas trace:
  UN: UN-763F8F61 (detector flags disagreement, never silently picks)
  DI: DI-8A5FCF4F (12-component, defence-in-depth episode detector)

Components
----------
correction_capture: turn audit-trail rows into normalised
    CorrectionEvent records keyed to a site and a correction_target.
scorer_retrain: per-site logistic-regression weight update over
    hand-engineered features. Pure function on a list of
    CorrectionEvent + the previous weight vector.
champion_challenger: evaluate a candidate weight vector against the
    labelled regression cohort; only promote if precision and recall
    both >= the current champion's scores by a configurable margin.
"""

from libs.episode_learning.correction_capture import (
    CorrectionEvent,
    capture_corrections_from_audit,
)
from libs.episode_learning.scorer_retrain import (
    ScorerWeights,
    retrain_site_scorer,
)
from libs.episode_learning.champion_challenger import (
    EvaluationResult,
    PromotionDecision,
    evaluate_challenger,
)

__all__ = [
    "CorrectionEvent",
    "capture_corrections_from_audit",
    "ScorerWeights",
    "retrain_site_scorer",
    "EvaluationResult",
    "PromotionDecision",
    "evaluate_challenger",
]
