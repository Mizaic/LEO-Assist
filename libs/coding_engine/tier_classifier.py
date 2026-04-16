"""Three-tier decision engine for autonomous and HITL coding.

Classifies each entity into one of three tiers based on assertion, context
detection status, terminology confidence, surface form status, and the
extractor's self-rated confidence.

Tier 1 -- auto-code: high-trust items coded without human review.
Tier 2 -- code with audit flag (autonomous) / review queue (HITL).
Tier 3 -- do not code (autonomous) / review queue (HITL).

Per-semantic-tag thresholds
---------------------------
Different SNOMED semantic domains have very different ambiguity profiles. A
disorder often has an exact FSN match at high score and can auto-code early;
an ``observable entity`` typically needs an exact FSN-level match before we
should commit. ``_TIER_THRESHOLDS`` captures this calibration.

Extractor confidence fusion
---------------------------
The LLM-based extractor now emits a self-rated confidence in ``[0, 1]``. The
effective score used for tier gating is ``min(terminology_score, ext_conf)``
so the classifier cannot auto-code a weakly-extracted entity even when the
terminology match happens to be high, but a near-1.0 self-rating does not
multiplicatively depress a legitimately high terminology score.

Low extractor confidence is also blocked via a hard floor
(``_TIER1_EXTRACTOR_CONFIDENCE_FLOOR``) -- below that the classifier caps at
tier 2 with reason ``low_extractor_confidence``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _TierThresholds:
    tier1: float
    tier2: float


# Per-semantic-tag (lower-cased, space-separated) thresholds. Missing tags
# fall back to ``_DEFAULT_TIER_THRESHOLDS``. Raise the tier-1 bar for
# domains where a wrong auto-code is high impact (drugs, observable
# parameters) and lower it for disorders where a high FSN match is very
# trustworthy.
_TIER_THRESHOLDS: dict[str, _TierThresholds] = {
    "disorder": _TierThresholds(tier1=0.92, tier2=0.70),
    "finding": _TierThresholds(tier1=0.93, tier2=0.70),
    "situation": _TierThresholds(tier1=0.93, tier2=0.70),
    "procedure": _TierThresholds(tier1=0.94, tier2=0.72),
    "substance": _TierThresholds(tier1=0.96, tier2=0.78),
    "product": _TierThresholds(tier1=0.97, tier2=0.80),
    "medicinal product": _TierThresholds(tier1=0.97, tier2=0.80),
    "clinical drug": _TierThresholds(tier1=0.97, tier2=0.80),
    "observable entity": _TierThresholds(tier1=0.96, tier2=0.75),
    "regime/therapy": _TierThresholds(tier1=0.95, tier2=0.75),
    "staging scale": _TierThresholds(tier1=0.95, tier2=0.72),
    "body structure": _TierThresholds(tier1=0.95, tier2=0.72),
}

_DEFAULT_TIER_THRESHOLDS = _TierThresholds(tier1=0.95, tier2=0.70)

# Minimum extractor confidence required to ever be considered for tier-1
# auto-coding. Below this the classifier caps the entity at tier 2, even
# when the terminology score would otherwise qualify.
_TIER1_EXTRACTOR_CONFIDENCE_FLOOR = 0.80

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


def _thresholds_for(semantic_tag: str) -> _TierThresholds:
    key = (semantic_tag or "").strip().lower().replace("_", " ")
    return _TIER_THRESHOLDS.get(key, _DEFAULT_TIER_THRESHOLDS)


def _effective_score(terminology_score: float, extractor_confidence: float) -> float:
    t = max(0.0, min(1.0, float(terminology_score)))
    c = max(0.0, min(1.0, float(extractor_confidence)))
    return min(t, c)


def classify_tier(
    *,
    assertion: str,
    context_failed: bool,
    terminology_score: float,
    surface_form_status: str,
    coding_mode: str,
    disorder_verdict: str = "",
    semantic_tag: str = "",
    extractor_confidence: float = 1.0,
    assertion_parity_failed: bool = False,
) -> TierDecision:
    """Classify an entity into a confidence tier.

    Args:
        assertion: Final assertion applied to the entity.
        context_failed: ConText raised an exception during detection.
        terminology_score: Best terminology/surface-form match score (0-1).
        surface_form_status: 'approved', 'pending', or '' (no match).
        coding_mode: 'hitl' or 'autonomous'.
        disorder_verdict: DisorderVerdict value if entity is a disorder.
        semantic_tag: SNOMED semantic tag used to select per-tag thresholds.
        extractor_confidence: Extractor self-rated confidence in [0, 1].
        assertion_parity_failed: True when the LLM extractor and the
            post-processing stack disagreed on the assertion. Caps the
            entity at tier 2 so a human confirms the resolved value.

    Returns:
        TierDecision with tier number, decision string, and reason.
    """
    is_autonomous = coding_mode == "autonomous"

    # -- Tier 3 gates: these always prevent auto-coding --

    if context_failed:
        return _tier3(is_autonomous, "context_failure")

    if disorder_verdict == "informational":
        return _tier3(is_autonomous, "informational")

    if disorder_verdict in {"uncertain", "gate_failed"}:
        return _tier3(is_autonomous, "uncertain_assertion")

    if assertion in {"absent", "declined", "cancelled", "planned", "hypothetical"}:
        return _tier3(is_autonomous, "non_codeable_assertion")

    if assertion == "possible":
        return _tier3(is_autonomous, "uncertain_assertion")

    thresholds = _thresholds_for(semantic_tag)
    effective = _effective_score(terminology_score, extractor_confidence)

    # -- Tier 1 gates: high-trust auto-code --

    tier1_blocked_reason = ""
    if assertion == "present" and not context_failed:
        if assertion_parity_failed:
            tier1_blocked_reason = "assertion_parity"
        elif extractor_confidence < _TIER1_EXTRACTOR_CONFIDENCE_FLOOR:
            tier1_blocked_reason = "low_extractor_confidence"
        elif effective >= thresholds.tier1:
            if surface_form_status == "approved":
                return TierDecision(
                    tier=1,
                    decision="auto_coded",
                    reason="surface_form_match",
                )
            return TierDecision(
                tier=1,
                decision="auto_coded",
                reason="high_confidence",
            )

    # -- Tier 2: medium confidence, qualifier assertions, or tier-1 blocked --

    if assertion in _QUALIFIER_ASSERTIONS:
        return _tier2(is_autonomous, "qualifier_assertion")

    if tier1_blocked_reason:
        return _tier2(is_autonomous, tier1_blocked_reason)

    if assertion == "present" and effective >= thresholds.tier2:
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
