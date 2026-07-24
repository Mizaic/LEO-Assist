"""Structured-first Situation source selection (D3.1-D3.2).

Atlas trace:
  DO: DO-FE774247
  DI: DI-ED65569C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-FE774247")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REASON_RESULT_VERSION = "1.0"


@dataclass
class ReferralReasonEvidence:
    reason_text: str
    source_type: str
    source_id: str
    chunk_id: str | None = None
    evidence_text: str | None = None
    detector_version: str = REASON_RESULT_VERSION
    run_id: str | None = None


@dataclass
class SituationSourceResult:
    headline: str
    structured_priority: str | None = None
    source_precedence: list[str] = field(default_factory=list)
    referral_reason: ReferralReasonEvidence | None = None
    letter_extract: str | None = None


def build_structured_situation(
    *,
    referral_request: dict[str, Any] | None,
    referral_reason: ReferralReasonEvidence | None,
    trigger_scoped_letter: str | None,
    run_id: str | None = None,
) -> SituationSourceResult:
    """Prefer ReferralRequest/eRS reason; fallback to trigger-scoped evidence."""
    precedence: list[str] = []
    rr = referral_request or {}
    reason = str(rr.get("reason") or "").strip()
    priority = str(rr.get("priority") or "").strip() or None
    if reason:
        precedence.append("referral_request.reason")
        evidence = ReferralReasonEvidence(
            reason_text=reason,
            source_type="ReferralRequest",
            source_id=str(rr.get("id") or ""),
            run_id=run_id,
        )
        return SituationSourceResult(
            headline=reason,
            structured_priority=priority,
            source_precedence=precedence,
            referral_reason=evidence,
        )

    if referral_reason and referral_reason.reason_text.strip():
        precedence.append("referral_reason_evidence")
        return SituationSourceResult(
            headline=referral_reason.reason_text.strip(),
            structured_priority=priority,
            source_precedence=precedence,
            referral_reason=referral_reason,
        )

    letter = str(trigger_scoped_letter or "").strip()
    if letter:
        precedence.append("trigger_scoped_letter_extract")
        return SituationSourceResult(
            headline=letter[:400],
            structured_priority=priority,
            source_precedence=precedence,
            letter_extract=letter,
        )

    return SituationSourceResult(
        headline="Referral reason not documented in structured or letter sources.",
        structured_priority=priority,
        source_precedence=["missing"],
    )


def reason_evidence_to_dict(evidence: ReferralReasonEvidence) -> dict[str, Any]:
    return {
        "reason_text": evidence.reason_text,
        "source_type": evidence.source_type,
        "source_id": evidence.source_id,
        "chunk_id": evidence.chunk_id,
        "evidence_text": evidence.evidence_text,
        "detector_version": evidence.detector_version,
        "run_id": evidence.run_id,
        "result_version": REASON_RESULT_VERSION,
    }
