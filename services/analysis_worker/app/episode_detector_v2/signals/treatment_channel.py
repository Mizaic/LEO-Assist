"""Treatment-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

STUB in v1 of v2: returns no signals. Treatment-channel logic
(chemotherapy / radiotherapy / oncology medications implying confirmed
diagnosis) lands in a later minor of v2 because it requires a curated
medication ontology mapping. Returning an empty list keeps the
downstream pipeline correct -- treatment-anchored episodes are simply
unavailable until the channel is real.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Signal, TimelineEvent


def extract_treatment_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """STUB: returns empty list."""
    _ = list(events)
    return []
