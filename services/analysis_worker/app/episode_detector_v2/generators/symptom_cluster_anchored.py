"""Symptom-cluster anchored candidate generator.

Atlas trace:
  DI: DI-8A5FCF4F

STUB in v1 of v2: returns no candidates. The text channel that would
feed this generator is itself a stub. This stub keeps the call-site
clean and lets the resolver and coverage check operate normally.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..types import CandidateEpisode, Signal, TimelineEvent


def generate_symptom_cluster_anchored(
    *,
    patient_id: str,
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
) -> list[CandidateEpisode]:
    """STUB: returns empty list."""
    _ = (patient_id, list(events), list(signals))
    return []
