"""Treatment-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

Minimal treatment evidence for v2. Curated oncology medication ontology
is still future work, but explicit breast-surgeon endocrine therapy is a
high-specificity breast-cancer treatment signal and can safely confirm
episode intent when diagnosis coding has been backfilled.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Signal, TimelineEvent


def extract_treatment_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Emit high-specificity treatment signals."""

    out: list[Signal] = []
    for event in events:
        text = " ".join((event.text_snippet or "").lower().split())
        if _is_breast_endocrine_treatment(text):
            out.append(
                Signal(
                    channel="treatment",
                    encounter_id=event.encounter_id,
                    site_key="breast",
                    role="treatment",
                    intent="confirmed",
                    confidence=0.85,
                    citation="Treatment mention: letrozole commenced by breast surgeon",
                )
            )
    return out


def _is_breast_endocrine_treatment(text: str) -> bool:
    if "letrozole" not in text:
        return False
    return any(
        phrase in text
        for phrase in (
            "pt commenced on letrozole",
            "commenced on letrozole",
        )
    ) and any(
        phrase in text
        for phrase in (
            "breast surgeon",
            "breast clinic letter",
        )
    )
