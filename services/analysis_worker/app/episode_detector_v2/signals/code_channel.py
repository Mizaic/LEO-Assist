"""Code-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

REAL implementation for breast (uses BREAST_SNOMED_* sets in
``site_keys``). For non-breast sites the extractor emits no signals --
this is the day-one stub behaviour confirmed in the plan.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..site_keys import (
    BREAST_SNOMED_BENIGN_CLOSURE,
    BREAST_SNOMED_CONFIRMED,
    BREAST_SNOMED_SUSPECTED,
    SITE_BREAST,
    site_intent_for_suspected_concept,
)
from ..types import Signal, TimelineEvent


def _classify_breast(concept_id: str) -> tuple[str, str, float] | None:
    """Return (site_key, intent, confidence) or None if not a breast code."""
    cid = concept_id.strip()
    if not cid:
        return None
    if cid in BREAST_SNOMED_CONFIRMED:
        return SITE_BREAST, "confirmed", 0.95
    if cid in BREAST_SNOMED_SUSPECTED:
        return SITE_BREAST, "suspected", 0.80
    if cid in BREAST_SNOMED_BENIGN_CLOSURE:
        return SITE_BREAST, "ruled_out", 0.70
    return None


def _classify_other_sites(concept_id: str) -> tuple[str, str, float] | None:
    """Return (site_key, intent, confidence) from the cross-site registry."""
    match = site_intent_for_suspected_concept(concept_id)
    if match is None:
        return None
    site_key, intent = match
    confidence = 0.85 if intent == "confirmed" else 0.70
    return site_key, intent, confidence


def _classify(concept_id: str) -> tuple[str, str, float] | None:
    """Breast-first then cross-site lookup -- breast wins on collision
    so the breast confidence calibration is preserved.
    """
    return _classify_breast(concept_id) or _classify_other_sites(concept_id)


def _role_from_assertion(assertion: str | None) -> str:
    norm = (assertion or "").lower()
    if "fam" in norm:
        return "family_history"
    if "hist" in norm:
        return "history"
    if "neg" in norm:
        return "outcome"
    return "diagnosis"


def extract_code_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Emit one Signal per coded entity that maps to a known site.

    The function is deterministic and side-effect free. It is the
    silent-drop fail-safe for stub sites: even though they have no
    candidate generator yet, the code-channel signal makes the
    encounter visible to the coverage check.
    """
    out: list[Signal] = []
    for event in events:
        for code in event.coded_entities:
            concept_id = str(code.get("concept_id") or "")
            classification = _classify(concept_id)
            if classification is None:
                continue
            site_key, intent, confidence = classification
            assertion = code.get("assertion")
            if (
                isinstance(assertion, str)
                and assertion.lower() in {"negated", "ruled_out", "negative"}
            ):
                intent = "ruled_out"
                confidence = max(confidence, 0.85)
            out.append(
                Signal(
                    channel="code",
                    encounter_id=event.encounter_id,
                    site_key=site_key,
                    role=_role_from_assertion(code.get("role") or assertion),
                    intent=intent,
                    confidence=confidence,
                    citation=(
                        f"SNOMED {concept_id} "
                        f"({code.get('display_name') or 'unknown term'})"
                    ),
                )
            )
    return out
