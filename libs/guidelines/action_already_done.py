"""Drop guideline actions the patient has already completed.

A receiving service should not be told to offer a faecal immunochemical
test (FIT) kit when the record already has a FIT result. Referral
actions stay in place: the current 2-week-wait referral is often coded
on the same encounter, so dropping it would hide the rule that should
lead.

A finding or observation counts as the procedure when SNOMED Interprets
or Has component links them, or when they sit in a curated family.

Atlas trace:
  DI: DI-B3B44F09
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B3B44F09")
"""

from __future__ import annotations

from typing import Any

from libs.guidelines.investigation_family import (
    FIT_KIT_PROCEDURE_ID,
    RelatedLookup,
    evidence_ids_for_action,
    patient_fact_ids,
    reverse_action_match,
)

_REFERRAL_NAME_TOKENS = (
    "referral",
    "refer to",
    "fast track",
    "2 week wait",
    "2-week wait",
    "two week wait",
    "2ww",
    "suspected cancer",
)
_FIT_KIT_NAME_TOKENS = (
    "faecal immunochemical",
    "fecal immunochemical",
    "fit kit",
)


def is_referral_action(action: dict[str, Any] | None) -> bool:
    """Return True when the action is a referral, not a test to offer."""
    if not action:
        return False
    if str(action.get("strength") or "").lower() == "refer":
        return True
    name = str(action.get("name") or "").lower()
    return any(token in name for token in _REFERRAL_NAME_TOKENS)


def is_fit_kit_action(action: dict[str, Any] | None) -> bool:
    """Return True when the action is to provide a FIT kit."""
    if not action:
        return False
    concept_id = str(action.get("concept_id") or "")
    if concept_id == FIT_KIT_PROCEDURE_ID:
        return True
    name = str(action.get("name") or "").lower()
    return any(token in name for token in _FIT_KIT_NAME_TOKENS)


def action_already_done(
    action: dict[str, Any] | None,
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
    related_lookup: RelatedLookup | None = None,
) -> bool:
    """Return True when this action should not be recommended again."""
    if not action or is_referral_action(action):
        return False
    concept_id = str(action.get("concept_id") or "").strip()
    facts = patient_fact_ids(patient_codes, observations)
    if not facts:
        return False
    evidence = _action_evidence(action, concept_id, related_lookup)
    if evidence & facts:
        return True
    if related_lookup and concept_id:
        return reverse_action_match(concept_id, facts, related_lookup)
    return False


def _action_evidence(
    action: dict[str, Any],
    concept_id: str,
    related_lookup: RelatedLookup | None,
) -> set[str]:
    related = related_lookup(concept_id) if related_lookup and concept_id else None
    evidence = evidence_ids_for_action(concept_id, related=related)
    for extra in action.get("already_done_evidence_ids") or []:
        text = str(extra).strip()
        if text:
            evidence.add(text)
    if is_fit_kit_action(action):
        evidence |= evidence_ids_for_action(FIT_KIT_PROCEDURE_ID, related=related)
    return evidence


def _rule_actions(rule: dict[str, Any]) -> list[dict[str, Any]]:
    actions = list(rule.get("actions") or [])
    if actions:
        return [item for item in actions if isinstance(item, dict)]
    single = rule.get("action")
    return [single] if isinstance(single, dict) else []


def remaining_actions(
    rule: dict[str, Any],
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
    related_lookup: RelatedLookup | None = None,
) -> list[dict[str, Any]]:
    """Return actions that are still worth recommending."""
    kept: list[dict[str, Any]] = []
    for action in _rule_actions(rule):
        if not action_already_done(action, patient_codes, observations, related_lookup):
            kept.append(action)
    return kept


def all_actions_already_done(
    rule: dict[str, Any],
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
    related_lookup: RelatedLookup | None = None,
) -> bool:
    """Return True when every action on the rule has already been done."""
    actions = _rule_actions(rule)
    if not actions:
        return False
    return not remaining_actions(rule, patient_codes, observations, related_lookup)


def apply_already_done_filter(
    payload: dict[str, Any],
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
    related_lookup: RelatedLookup | None = None,
) -> dict[str, Any] | None:
    """Keep remaining actions, or None when nothing is left to recommend."""
    actions = _rule_actions(payload)
    if not actions:
        return payload
    kept = remaining_actions(payload, patient_codes, observations, related_lookup)
    if not kept:
        return None
    updated = dict(payload)
    updated["actions"] = kept
    updated["action"] = kept[0]
    return updated


def mark_already_done_actions(
    payload: dict[str, Any],
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
    related_lookup: RelatedLookup | None = None,
) -> dict[str, Any]:
    """Keep the match and flag completed actions instead of hiding them."""
    updated = dict(payload)
    actions = _rule_actions(payload)
    if not actions:
        updated["already_actioned"] = False
        return updated
    marked: list[dict[str, Any]] = []
    for action in actions:
        item = dict(action)
        item["already_done"] = action_already_done(
            action, patient_codes, observations, related_lookup
        )
        marked.append(item)
    updated["actions"] = marked
    updated["action"] = marked[0]
    updated["already_actioned"] = all(item["already_done"] for item in marked)
    return updated


def rule_already_actioned(rule: dict[str, Any]) -> bool:
    """True when the rule match should sit behind Already done."""
    if rule.get("already_actioned"):
        return True
    actions = _rule_actions(rule)
    return bool(actions) and all(bool(item.get("already_done")) for item in actions)


def split_already_actioned_rules(
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split matches into still-open rules and completed rules."""
    open_rules: list[dict[str, Any]] = []
    done_rules: list[dict[str, Any]] = []
    for rule in rules:
        if rule_already_actioned(rule):
            done_rules.append(rule)
        else:
            open_rules.append(rule)
    return open_rules, done_rules
