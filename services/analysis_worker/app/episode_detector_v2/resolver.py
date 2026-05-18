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
from dataclasses import replace
from datetime import date

from .aggregator import AggregatedCandidate
from .types import Signal

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
    resolved = [_merge_cluster(cluster) for cluster in clusters]
    return sorted(resolved, key=lambda a: (a.candidate.site_key, a.candidate.candidate_id))


def _same_cluster(left: AggregatedCandidate, right: AggregatedCandidate) -> bool:
    l_cand = left.candidate
    r_cand = right.candidate
    if l_cand.site_key != r_cand.site_key:
        return False
    if l_cand.anchor_event_id and l_cand.anchor_event_id == r_cand.anchor_event_id:
        return True
    win_overlap = _encounter_overlap(l_cand.encounter_ids, r_cand.encounter_ids)
    if win_overlap >= _CLUSTER_OVERLAP_THRESHOLD:
        return True
    l_date = l_cand.anchor_date
    r_date = r_cand.anchor_date
    if l_date is not None and r_date is not None:
        anchor_gap = abs((l_date - r_date).days)
        if anchor_gap <= _CLUSTER_ANCHOR_DAYS:
            return True
        return False
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
    return sorted(
        cluster,
        key=lambda agg: (
            -agg.evidence_weight,
            -_GENERATOR_PRIORITY.get(agg.candidate.generator, 0),
            -(agg.candidate.anchor_date is not None),
            -(
                agg.candidate.anchor_date.toordinal()
                if agg.candidate.anchor_date is not None
                else 0
            ),
            len(agg.candidate.encounter_ids),
            agg.candidate.candidate_id,
        ),
    )[0]


def _ordered_encounter_union(cluster: list[AggregatedCandidate]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for agg in sorted(
        cluster,
        key=lambda a: (
            a.candidate.anchor_date or date.min,
            a.candidate.anchor_event_id,
        ),
    ):
        for eid in agg.candidate.encounter_ids:
            if eid not in seen:
                seen.add(eid)
                ordered.append(eid)
    return ordered


def _merge_supporting_signals(cluster: list[AggregatedCandidate]) -> list[Signal]:
    merged: list[Signal] = []
    seen: set[tuple[str, str, str, str]] = set()
    for agg in cluster:
        for sig in agg.candidate.supporting_signals:
            key = (sig.channel, sig.encounter_id, sig.site_key, sig.intent)
            if key in seen:
                continue
            seen.add(key)
            merged.append(sig)
    return merged


def _merge_signals_by_channel(
    cluster: list[AggregatedCandidate],
) -> dict[str, list[Signal]]:
    all_signals: list[Signal] = []
    for agg in cluster:
        for sigs in agg.signals_by_channel.values():
            all_signals.extend(sigs)
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[Signal] = []
    for sig in all_signals:
        key = (sig.channel, sig.encounter_id, sig.site_key, sig.intent)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sig)
    by_channel: dict[str, list[Signal]] = {}
    for sig in deduped:
        by_channel.setdefault(sig.channel, []).append(sig)
    return by_channel


def _merge_cluster(cluster: list[AggregatedCandidate]) -> AggregatedCandidate:
    if len(cluster) == 1:
        return cluster[0]
    best = _best_candidate(cluster)
    by_channel = _merge_signals_by_channel(cluster)
    diversity = len(by_channel)
    flat = [s for sigs in by_channel.values() for s in sigs]
    weight = round(
        sum(s.confidence for s in flat) * (1.0 + 0.1 * (diversity - 1)),
        4,
    )
    merged_cand = replace(
        best.candidate,
        encounter_ids=_ordered_encounter_union(cluster),
        supporting_signals=_merge_supporting_signals(cluster),
    )
    gens = tuple(sorted({agg.candidate.generator for agg in cluster}))
    return AggregatedCandidate(
        candidate=merged_cand,
        evidence_weight=weight,
        channel_diversity=diversity,
        signals_by_channel=by_channel,
        consensus_generators=gens,
    )
