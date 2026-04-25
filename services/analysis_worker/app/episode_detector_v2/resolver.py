"""Conflict resolver.

Atlas trace:
  DI: DI-8A5FCF4F

Greedy assignment: for each (site_key, anchor cluster) take the highest
evidence-weighted candidate. The assignment is _per site_, so a patient
can have one breast episode AND one lung episode without competing.

A future minor will swap this for the Hungarian algorithm; the
interface stays stable.
"""

from __future__ import annotations

from collections.abc import Sequence

from .aggregator import AggregatedCandidate

_CLUSTER_OVERLAP_THRESHOLD = 0.45
_CLUSTER_ANCHOR_DAYS = 45
_GENERATOR_PRIORITY = {
    "referral_anchored": 5,
    "diagnosis_anchored": 4,
    "site_cohort_anchored": 3,
    "treatment_anchored": 2,
    "symptom_cluster_anchored": 1,
}


def resolve_conflicts(
    aggregated: Sequence[AggregatedCandidate],
) -> list[AggregatedCandidate]:
    """Pick the best candidate per same-site anchor cluster.

    Deterministic: ties broken by candidate_id ascending.
    """
    clusters: list[list[AggregatedCandidate]] = []
    for agg in aggregated:
        for cluster in clusters:
            if any(_same_cluster(agg, existing) for existing in cluster):
                cluster.append(agg)
                break
        else:
            clusters.append([agg])
    resolved = [_best_candidate(cluster) for cluster in clusters]
    return sorted(resolved, key=lambda a: (a.candidate.site_key, a.candidate.candidate_id))


def _same_cluster(left: AggregatedCandidate, right: AggregatedCandidate) -> bool:
    l_cand = left.candidate
    r_cand = right.candidate
    if l_cand.site_key != r_cand.site_key:
        return False
    if l_cand.anchor_event_id and l_cand.anchor_event_id == r_cand.anchor_event_id:
        return True
    l_date = l_cand.anchor_date
    r_date = r_cand.anchor_date
    if l_date is not None and r_date is not None:
        if abs((l_date - r_date).days) <= _CLUSTER_ANCHOR_DAYS:
            return True
    return _encounter_overlap(_signal_ids(left), _signal_ids(right)) >= (
        _CLUSTER_OVERLAP_THRESHOLD
    )


def _signal_ids(aggregated: AggregatedCandidate) -> list[str]:
    return [
        sig.encounter_id
        for signals in aggregated.signals_by_channel.values()
        for sig in signals
        if getattr(sig, "role", "") != "context_milestone"
    ]


def _encounter_overlap(left: list[str], right: list[str]) -> float:
    l_ids = set(left)
    r_ids = set(right)
    if not l_ids or not r_ids:
        return 0.0
    return len(l_ids & r_ids) / min(len(l_ids), len(r_ids))


def _best_candidate(cluster: list[AggregatedCandidate]) -> AggregatedCandidate:
    return max(
        cluster,
        key=lambda agg: (
            agg.evidence_weight,
            _GENERATOR_PRIORITY.get(agg.candidate.generator, 0),
            agg.candidate.anchor_date is not None,
            agg.candidate.anchor_date,
            -len(agg.candidate.encounter_ids),
            agg.candidate.candidate_id,
        ),
    )
