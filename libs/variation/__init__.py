"""Unwarranted variation detection engine.

Atlas trace:
  UN: UN-86B5D433  Unwarranted variation detection across matched peer cohorts
  DI: DI-EF8EA3BD  Platform SHALL compute episode-level variation flags from
                   peer cohort milestone percentiles
  DO: DO-64B006B5  Unwarranted variation engine
  R:  R-31217EFA   Incorrect variation flag causes reviewer to miss or
                   over-investigate a pathway
  VT: VT-3B37176C  Unwarranted variation engine - acceptance verification

Public API:
  - MilestonePercentile, MilestoneObservation, VariationResult, AttributionResult
  - get_milestone_percentiles(client, community_id, scope, months)
  - score_episode(observations, percentiles, min_sample_size)
  - write_variation_result(client, result)
  - attribute_root_cause(client, patient_id, first_divergence)

Public constants:
  - DEFAULT_MIN_SAMPLE_SIZE: minimum cohort sample size before any flag is
    written. Lower cohort sizes return score_episode(...) = None.
"""

from libs.variation.attribution import AttributionResult, attribute_root_cause
from libs.variation.cohort_percentiles import (
    MilestonePercentile,
    get_milestone_percentiles,
)
from libs.variation.scorer import (
    DEFAULT_MIN_SAMPLE_SIZE,
    MilestoneObservation,
    VariationResult,
    score_episode,
)
from libs.variation.writer import write_attribution_result, write_variation_result

__all__ = [
    "AttributionResult",
    "DEFAULT_MIN_SAMPLE_SIZE",
    "MilestoneObservation",
    "MilestonePercentile",
    "VariationResult",
    "attribute_root_cause",
    "get_milestone_percentiles",
    "score_episode",
    "write_attribution_result",
    "write_variation_result",
]
