"""Treatment-anchored candidate generator.

Atlas trace:
  DI: DI-8A5FCF4F

STUB in v1 of v2: returns no candidates. Upstream treatment-channel
signals are themselves a stub.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..types import CandidateEpisode, Signal, TimelineEvent


def generate_treatment_anchored(
    *,
    patient_id: str,
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
) -> list[CandidateEpisode]:
    """STUB: returns empty list."""
    _ = (patient_id, list(events), list(signals))
    return []
