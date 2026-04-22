"""Text-channel signal extractor (LLM-based site/role/temporal anchoring).

Atlas trace:
  DI: DI-8A5FCF4F

STUB in this version: emits an empty list. The text channel will be
filled in once the breast-only LLM extractor has been built and
benchmarked against the regression cohort. See plan section
'Phase 1 -- Skeleton detector', signals/text_channel.py: stub returns
empty; Atlas DI tracked for v2 (the next minor of the v2 system).

The stub keeps the same signature so the runner does not branch on
which extractors are real.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Signal, TimelineEvent


def extract_text_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """STUB: returns empty list -- safe default for the cold-start phase."""
    _ = list(events)
    return []
