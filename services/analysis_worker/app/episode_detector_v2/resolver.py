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


def resolve_conflicts(
    aggregated: Sequence[AggregatedCandidate],
) -> list[AggregatedCandidate]:
    """Pick the best candidate per (site_key, anchor_event_id).

    Deterministic: ties broken by candidate_id ascending.
    """
    by_key: dict[tuple[str, str], AggregatedCandidate] = {}
    for agg in aggregated:
        cand = agg.candidate
        key = (cand.site_key, cand.anchor_event_id or cand.candidate_id)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = agg
            continue
        if agg.evidence_weight > existing.evidence_weight:
            by_key[key] = agg
        elif (
            agg.evidence_weight == existing.evidence_weight
            and cand.candidate_id < existing.candidate.candidate_id
        ):
            by_key[key] = agg
    return sorted(
        by_key.values(),
        key=lambda a: (a.candidate.site_key, a.candidate.candidate_id),
    )
