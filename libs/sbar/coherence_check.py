"""SBAR coherence check.

Atlas trace:
  DI: DI-CC0BD732 (Per-episode SBAR with cross-section coherence)

Detects two failure modes that broke patient 9990001004:

1. ``narrative_contradiction`` -- the Assessment (narrative) says one
   thing but the Recommendation says the opposite. Example: assessment
   notes "no current evidence of malignancy" while recommendation
   includes "urgent oncology referral".
2. ``code_narrative_drift`` -- the canonical episode code says the
   episode is for site X but the SBAR narrative names site Y.

These are deterministic string + token checks; no LLM. The output is a
list of ``CoherenceFlag`` records the orchestrator can attach to the
:Assessment via ``a.coherence_flags`` JSON.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


_NEGATION_PATTERNS = (
    r"\bno (?:current )?evidence of\b",
    r"\bnot (?:consistent|suggestive|indicative) of\b",
    r"\bbenign\b",
    r"\bruled out\b",
    r"\bnegative for\b",
)

_RECOMMEND_URGENT = (
    "urgent referral",
    "two-week wait",
    "2ww",
    "fast-track",
    "oncology referral",
    "biopsy",
    "mdt",
    "multi-disciplinary",
)


@dataclass(frozen=True)
class CoherenceFlag:
    code: str
    severity: str  # low | medium | high
    summary: str
    citation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _has_any(text: str, needles: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for n in needles:
        if n in lowered:
            return n
    return None


def _has_regex(text: str, patterns: tuple[str, ...]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def check_narrative_contradiction(
    assessment_md: str, recommendation_md: str
) -> CoherenceFlag | None:
    """Flag when assessment denies cancer but recommendation escalates."""
    if not assessment_md or not recommendation_md:
        return None
    negation = _has_regex(assessment_md, _NEGATION_PATTERNS)
    if not negation:
        return None
    urgent = _has_any(recommendation_md, _RECOMMEND_URGENT)
    if not urgent:
        return None
    return CoherenceFlag(
        code="narrative_contradiction",
        severity="high",
        summary=(
            "Assessment text contains a negation phrase "
            f"({negation!r}) but Recommendation includes an "
            f"urgent action ({urgent!r}). Reviewer must reconcile."
        ),
        citation=f"assessment::{negation}; recommendation::{urgent}",
    )


def check_code_narrative_drift(
    canonical_concept_id: str | None,
    canonical_display_name: str,
    suspected_site: str,
    sbar_markdown: str,
) -> CoherenceFlag | None:
    """Flag when the canonical code site is not mentioned in the SBAR text."""
    if not canonical_concept_id or not sbar_markdown:
        return None
    site = (suspected_site or "").lower().strip()
    if not site or site == "unknown":
        return None
    text = sbar_markdown.lower()
    if site in text:
        return None
    display = (canonical_display_name or "").lower()
    if display and any(tok in text for tok in display.split() if len(tok) > 4):
        return None
    return CoherenceFlag(
        code="code_narrative_drift",
        severity="medium",
        summary=(
            f"Canonical code is for site '{suspected_site}' "
            f"({canonical_display_name or canonical_concept_id}) but "
            "the SBAR narrative does not mention this site."
        ),
        citation=f"canonical::{canonical_concept_id}",
    )


def run_coherence_checks(
    *,
    assessment_md: str,
    recommendation_md: str,
    sbar_markdown: str,
    canonical_concept_id: str | None,
    canonical_display_name: str,
    suspected_site: str,
) -> list[CoherenceFlag]:
    flags: list[CoherenceFlag] = []
    a = check_narrative_contradiction(assessment_md, recommendation_md)
    if a:
        flags.append(a)
    b = check_code_narrative_drift(
        canonical_concept_id,
        canonical_display_name,
        suspected_site,
        sbar_markdown,
    )
    if b:
        flags.append(b)
    return flags
