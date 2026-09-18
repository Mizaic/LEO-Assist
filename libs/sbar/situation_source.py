"""Structured-first Situation source selection (D3.1-D3.2).

Atlas trace:
  DO: DO-FE774247
  DI: DI-ED65569C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-FE774247")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from libs.completeness.logic_groups import collect_concept_ids
from libs.sbar.clinic_reason_fit import reason_matches_clinic
from libs.sbar.situation_headline import headline_from_coded_facts

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
    form_clinical_section: str | None = None,
    form_sections: list[Any] | None = None,
    coded_facts: list[dict[str, Any]] | None = None,
    completeness_groups: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> SituationSourceResult:
    """Prefer coded facts, then a clinic-matching reason, then the form."""
    rr = referral_request or {}
    priority = str(rr.get("priority") or "").strip() or None
    clinic = str(rr.get("clinic_type") or "")
    coded = headline_from_coded_facts(
        coded_facts,
        clinic_type=clinic,
        priority_concept_ids=collect_concept_ids(completeness_groups or []),
    )
    if coded:
        return SituationSourceResult(
            headline=coded,
            structured_priority=priority,
            source_precedence=["coded_facts"],
        )
    matched = _clinic_matching_reason(rr, referral_reason, clinic, run_id)
    if matched is not None:
        return matched
    section = _resolve_form_clinical_section(
        trigger_scoped_letter, form_clinical_section, form_sections
    )
    if section:
        return SituationSourceResult(
            headline=section[:400],
            structured_priority=priority,
            source_precedence=["form_clinical_section"],
            letter_extract=section,
        )
    return SituationSourceResult(
        headline="Referral reason not documented in structured or letter sources.",
        structured_priority=priority,
        source_precedence=["missing"],
    )


def _clinic_matching_reason(
    rr: dict[str, Any],
    referral_reason: ReferralReasonEvidence | None,
    clinic: str,
    run_id: str | None,
) -> SituationSourceResult | None:
    priority = str(rr.get("priority") or "").strip() or None
    reason = str(rr.get("reason") or "").strip()
    if reason and reason_matches_clinic(reason, clinic):
        evidence = ReferralReasonEvidence(
            reason_text=reason,
            source_type="ReferralRequest",
            source_id=str(rr.get("id") or ""),
            run_id=run_id,
        )
        return SituationSourceResult(
            headline=reason,
            structured_priority=priority,
            source_precedence=["referral_request.reason"],
            referral_reason=evidence,
        )
    recalled = str(getattr(referral_reason, "reason_text", "") or "").strip()
    if recalled and reason_matches_clinic(recalled, clinic):
        return SituationSourceResult(
            headline=recalled,
            structured_priority=priority,
            source_precedence=["referral_reason_evidence"],
            referral_reason=referral_reason,
        )
    return None


def _resolve_form_clinical_section(
    letter: str | None,
    form_clinical_section: str | None,
    form_sections: list[Any] | None,
) -> str:
    from libs.pipeline.document_role import clinical_letter_text
    from libs.sbar.referral_reason_match import extract_form_clinical_section

    explicit = str(form_clinical_section or "").strip()
    if explicit:
        return explicit
    clinical = clinical_letter_text(str(letter or "")).strip()
    if not clinical or not form_sections:
        return ""
    return str(extract_form_clinical_section(clinical, form_sections) or "").strip()


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
