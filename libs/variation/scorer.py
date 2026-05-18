"""Pure-Python variation scorer.

Atlas trace: DO-64B006B5 (see libs/variation/__init__.py).

Compares an episode's observed milestone intervals to peer cohort P25/P50/P75.
An episode is flagged when any observed interval is strictly above the peer
cohort P75 for that milestone pair -- i.e. the patient is waiting longer
between milestones than 75 percent of their matched peers. Short intervals
(below P25) are not flagged because faster-than-peer pathway progress is
not clinically harmful.

Pair-level comparison is suppressed when cohort sample_size is below
`min_sample_size` (default 20) -- this is the primary mitigation for
R-31217EFA (false-positive variation flags on small cohorts).

The scorer is side-effect free: it takes plain data structures and returns
a plain dataclass so the same logic can run in CI without Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from libs.variation.cohort_percentiles import MilestonePercentile


DEFAULT_MIN_SAMPLE_SIZE = 20


@dataclass(frozen=True)
class MilestoneObservation:
    """One observed interval between two milestones on a single episode."""

    from_step: str
    to_step: str
    interval_days: float
    observed_at: Optional[str] = None


@dataclass
class VariationResult:
    """Scored variation verdict for a single EpisodeOfCare."""

    episode_id: str
    community_id: int
    variation_flag: bool
    variation_score: float
    outlier_steps: List[str] = field(default_factory=list)
    first_divergence: Optional[str] = None
    observed_pairs: int = 0
    compared_pairs: int = 0


def _step_key(from_step: str, to_step: str) -> str:
    return f"{from_step}->{to_step}"


def _index_percentiles(
    percentiles: List[MilestonePercentile],
) -> Dict[Tuple[str, str], MilestonePercentile]:
    return {(p.from_step, p.to_step): p for p in percentiles}


def _observation_order(observations: List[MilestoneObservation]) -> List[str]:
    """Order observations by observed_at if present, else by input order.

    The earliest flagged step (by time) becomes first_divergence.
    """
    keyed = []
    for idx, obs in enumerate(observations):
        sort_key = (obs.observed_at or "", idx)
        keyed.append((sort_key, obs))
    keyed.sort(key=lambda kv: kv[0])
    return [_step_key(obs.from_step, obs.to_step) for _, obs in keyed]


def score_episode(
    episode_id: str,
    community_id: int,
    observations: List[MilestoneObservation],
    percentiles: List[MilestonePercentile],
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> Optional[VariationResult]:
    """Score one episode against its peer cohort percentiles.

    Returns None when no observation has a matching cohort pair with at
    least `min_sample_size` peers -- i.e. there is not enough evidence
    to write a flag either way. This is deliberate: writing a
    variation_flag=False on such cases would overclaim.
    """
    if not observations:
        return None
    index = _index_percentiles(percentiles)
    outliers: List[str] = []
    compared = 0
    for obs in observations:
        pct = index.get((obs.from_step, obs.to_step))
        if pct is None or pct.sample_size < min_sample_size:
            continue
        compared += 1
        if obs.interval_days > pct.p75:
            outliers.append(_step_key(obs.from_step, obs.to_step))
    if compared == 0:
        return None
    variation_score = len(outliers) / compared
    first_divergence = _first_divergence(observations, outliers)
    return VariationResult(
        episode_id=episode_id,
        community_id=community_id,
        variation_flag=bool(outliers),
        variation_score=round(variation_score, 4),
        outlier_steps=outliers,
        first_divergence=first_divergence,
        observed_pairs=len(observations),
        compared_pairs=compared,
    )


def _first_divergence(
    observations: List[MilestoneObservation],
    outliers: List[str],
) -> Optional[str]:
    if not outliers:
        return None
    outlier_set = set(outliers)
    for step in _observation_order(observations):
        if step in outlier_set:
            return step
    return outliers[0]
