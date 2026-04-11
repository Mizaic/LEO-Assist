"""Three-tier decision engine for autonomous and HITL coding.

Classifies each entity into one of three tiers based on assertion, context
detection status, terminology confidence, and surface form status.

Tier 1 -- auto-code: high-trust items coded without human review.
Tier 2 -- code with audit flag (autonomous) / review queue (HITL).
Tier 3 -- do not code (autonomous) / review queue (HITL).
"""

from __future__ import annotations

from dataclasses import dataclass

_TIER1_SCORE_THRESHOLD = 0.95
_TIER2_SCORE_THRESHOLD = 0.70
_AUTO_CODE_BLOCKED = frozenset(
    {
        "absent",
        "refuted",
        "declined",
        "cancelled",
        "planned",
        "hypothetical",
        "possible",
        "historical",
        "family",
    }
)
_QUALIFIER_ASSERTIONS = frozenset({"historical", "family"})


@dataclass(frozen=True)
class TierDecision:
    """Output of the tier classifier."""

    tier: int
    decision: str
    reason: str


def classify_tier(
    *,
    assertion: str,
    context_failed: bool,
    terminology_score: float,
    surface_form_status: str,
    coding_mode: str,
    disorder_verdict: str = "",
) -> TierDecision:
    """Classify an entity into a confidence tier.

    Args:
        assertion: ConText assertion (e.g. 'present', 'absent', 'possible').
        context_failed: True if ConText detection raised an exception.
        terminology_score: Best terminology/surface-form match score (0-1).
        surface_form_status: 'approved', 'pending', or '' (no match).
        coding_mode: 'hitl' or 'autonomous'.
        disorder_verdict: DisorderVerdict value if entity is a disorder.

    Returns:
        TierDecision with tier number, decision string, and reason.
    """
    is_autonomous = coding_mode == "autonomous"

    # -- Tier 3 gates: these always prevent auto-coding --

    if context_failed:
        return _tier3(is_autonomous, "context_failure")

    if disorder_verdict == "informational":
        return _tier3(is_autonomous, "informational")

    if disorder_verdict == "uncertain":
        return _tier3(is_autonomous, "uncertain_assertion")

    if assertion in {"absent", "declined", "cancelled", "planned", "hypothetical"}:
        return _tier3(is_autonomous, "non_codeable_assertion")

    if assertion == "possible":
        return _tier3(is_autonomous, "uncertain_assertion")

    # -- Tier 1 gates: high-trust auto-code --

    if assertion == "present" and not context_failed:
        if (
            surface_form_status == "approved"
            and terminology_score >= _TIER1_SCORE_THRESHOLD
        ):
            return TierDecision(
                tier=1,
                decision="auto_coded",
                reason="surface_form_match",
            )

        if terminology_score >= _TIER1_SCORE_THRESHOLD:
            return TierDecision(
                tier=1,
                decision="auto_coded",
                reason="high_confidence",
            )

    # -- Tier 2: medium confidence or qualifier assertions --

    if assertion in _QUALIFIER_ASSERTIONS:
        return _tier2(is_autonomous, "qualifier_assertion")

    if assertion == "present" and terminology_score >= _TIER2_SCORE_THRESHOLD:
        if surface_form_status == "pending":
            return _tier2(is_autonomous, "pending_surface_form")
        return _tier2(is_autonomous, "medium_confidence")

    # -- Everything else is Tier 3 --

    return _tier3(is_autonomous, "low_confidence")


def _tier2(is_autonomous: bool, reason: str) -> TierDecision:
    if is_autonomous:
        return TierDecision(tier=2, decision="coded_with_flag", reason=reason)
    return TierDecision(tier=2, decision="route_to_review", reason=reason)


def _tier3(is_autonomous: bool, reason: str) -> TierDecision:
    if is_autonomous:
        return TierDecision(tier=3, decision="not_coded", reason=reason)
    return TierDecision(tier=3, decision="route_to_review", reason=reason)
