"""Decide if we have enough reason-for-referral to check guidelines.

Atlas:
  DI: DI-EAFB2CC7
  DO: DO-A7019CCB
  VT: VT-6727E0DF
  Risk: R-AA3586B8
"""

from __future__ import annotations

from typing import Any

_CLINICAL_LABELS = frozenset({"situation", "finding", "disorder"})
_EXCLUDED_ASSERTIONS = frozenset(
    {"absent", "negated", "refuted", "family", "assertion_unverified"}
)
_REASON_SECTION_IDS = frozenset({"reason_for_referral", "reason"})


def required_form_not_assessable(completeness: dict[str, Any] | None) -> bool:
    """True when a required completeness group could not be scored."""
    if not completeness:
        return False
    for row in completeness.get("missing_groups") or []:
        if row.get("required") and row.get("outcome") == "not_assessable":
            return True
    return False


def has_usable_referral_reason(
    *,
    referral_reason: str | None = None,
    completeness: dict[str, Any] | None = None,
    section_hits: list[dict[str, Any]] | None = None,
    entities: list[dict[str, Any]] | None = None,
    form_clinical_section: str | None = None,
) -> bool:
    """True when a reason exists to check guidelines.

    A missing two-week-wait form is fine if few-shot extraction, the
    national e-RS reason box, or the referral-reason step already
    produced a presenting complaint.
    """
    if str(referral_reason or "").strip():
        return True
    if str(form_clinical_section or "").strip():
        return True
    if _reason_group_matched(completeness):
        return True
    if _reason_hit_filled(section_hits):
        return True
    return _has_present_clinical_fact(entities)


def missing_referral_reason(
    *,
    referral_reason: str | None = None,
    completeness: dict[str, Any] | None = None,
    section_hits: list[dict[str, Any]] | None = None,
    entities: list[dict[str, Any]] | None = None,
    form_clinical_section: str | None = None,
) -> bool:
    """True when we cannot check guidelines and need more information."""
    return not has_usable_referral_reason(
        referral_reason=referral_reason,
        completeness=completeness,
        section_hits=section_hits,
        entities=entities,
        form_clinical_section=form_clinical_section,
    )


def _reason_group_matched(completeness: dict[str, Any] | None) -> bool:
    for row in (completeness or {}).get("matched_groups") or []:
        if row.get("name") == "reason_for_referral_required" and row.get("matched"):
            return True
    return False


def _reason_hit_filled(section_hits: list[dict[str, Any]] | None) -> bool:
    for hit in section_hits or []:
        if str(hit.get("section_id") or "") not in _REASON_SECTION_IDS:
            continue
        if hit.get("checked") or str(hit.get("value") or "").strip():
            return True
    return False


def _has_present_clinical_fact(entities: list[dict[str, Any]] | None) -> bool:
    for entity in entities or []:
        label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
        if label not in _CLINICAL_LABELS:
            continue
        assertion = str(entity.get("assertion") or "present").lower()
        if assertion in _EXCLUDED_ASSERTIONS:
            continue
        if str(entity.get("text") or entity.get("term") or "").strip():
            return True
    return False
