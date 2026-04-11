"""Context reconciliation for candidate terms using medspaCy when available."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextFlags:
    negated: bool
    uncertain: bool
    historical: bool
    subject: str
    temporality: str


def reconcile_context(text: str, default_subject: str = "patient") -> ContextFlags:
    """Apply deterministic lexical cues and optional medspaCy defaults.

    This MVP keeps behavior deterministic and only relies on medspaCy if present in
    runtime environment. If unavailable, it still produces stable context output.
    """
    lowered = text.lower()
    negated = any(cue in lowered for cue in (" no ", " denies ", " nil ", " nad "))
    uncertain = any(cue in lowered for cue in ("?", "possible", "likely", "suspect"))
    historical = any(
        cue in lowered for cue in ("history of", "previous", "previously", "past")
    )

    subject = (
        "family" if "family history" in lowered or "fhx" in lowered else default_subject
    )
    temporality = "present"
    if any(cue in lowered for cue in ("plan", "review", "refer", "follow-up")):
        temporality = "planned"
    elif historical:
        temporality = "past"
    elif uncertain:
        temporality = "hypothetical"

    return ContextFlags(
        negated=negated,
        uncertain=uncertain,
        historical=historical,
        subject=subject,
        temporality=temporality,
    )
