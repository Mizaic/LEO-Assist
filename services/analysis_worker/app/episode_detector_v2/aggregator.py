"""Evidence aggregator.

Atlas trace:
  DI: DI-8A5FCF4F

Joins signals onto candidate episodes. Sums per-signal confidence into
an evidence weight, normalised by channel diversity (so a candidate
backed by code+pathway+result outscores three same-channel signals).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .types import CandidateEpisode, Signal


@dataclass
class AggregatedCandidate:
    candidate: CandidateEpisode
    evidence_weight: float
    channel_diversity: int
    signals_by_channel: dict[str, list[Signal]]
    # When the resolver merges a cluster, generators from all members (for tiering).
    consensus_generators: tuple[str, ...] | None = None


def aggregate_evidence(
    candidates: Sequence[CandidateEpisode],
    signals: Sequence[Signal],
) -> list[AggregatedCandidate]:
    """Attach signals to candidates by (site_key, encounter_id) join.

    Pure function. Returns one AggregatedCandidate per input candidate,
    even if the join finds no extra signals.
    """
    enriched: list[AggregatedCandidate] = []
    signal_index: dict[tuple[str, str], list[Signal]] = {}
    for sig in signals:
        signal_index.setdefault((sig.site_key, sig.encounter_id), []).append(sig)

    for cand in candidates:
        all_signals: list[Signal] = list(cand.supporting_signals)
        for enc_id in cand.encounter_ids:
            for sig in signal_index.get((cand.site_key, enc_id), []):
                all_signals.append(sig)
        deduped: list[Signal] = []
        seen: set[tuple[str, str, str, str]] = set()
        for sig in all_signals:
            key = (sig.channel, sig.encounter_id, sig.site_key, sig.intent)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(sig)

        by_channel: dict[str, list[Signal]] = {}
        for sig in deduped:
            by_channel.setdefault(sig.channel, []).append(sig)

        diversity = len(by_channel)
        weight = sum(s.confidence for s in deduped) * (1.0 + 0.1 * (diversity - 1))

        enriched.append(
            AggregatedCandidate(
                candidate=cand,
                evidence_weight=round(weight, 4),
                channel_diversity=diversity,
                signals_by_channel=by_channel,
            )
        )
    return enriched
