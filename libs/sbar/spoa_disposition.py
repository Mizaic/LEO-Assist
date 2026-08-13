"""Deterministic advisory SPoA disposition mapping for referral assessment.

Atlas trace:
  DO: DO-EBD03C23
  DI: DI-45F32638
"""

from __future__ import annotations

from typing import Any

SPOA_DISPOSITIONS: tuple[str, ...] = (
    "discussion_with_primary_care",
    "straight_to_test",
    "outpatient_appointment",
    "procedure",
    "refer_to_alternative_service",
    "other_spoa",
    "next_internal_spoa",
)

_DISPOSITION_LABELS: dict[str, str] = {
    "discussion_with_primary_care": "Discussion with primary care",
    "straight_to_test": "Straight to test",
    "outpatient_appointment": "Outpatient appointment",
    "procedure": "Procedure",
    "refer_to_alternative_service": "Refer to alternative service",
    "other_spoa": "Other SPoA",
    "next_internal_spoa": "Next internal SPoA",
}

_TIME_CRITICAL = {"immediate", "very_urgent", "2ww", "urgent"}
_DIAGNOSTIC_TOKENS = (
    "x-ray",
    "xray",
    "scan",
    "mammogram",
    "ultrasound",
    "test",
    "imaging",
)
# Deliberately specific invasive-procedure names -- NOT the bare word
# "procedure". SNOMED CT tags almost every action concept under the
# procedure hierarchy with a trailing "(procedure)" semantic tag,
# including referrals (e.g. "Fast track referral for suspected upper
# gastrointestinal cancer (procedure)") and imaging (e.g. "Plain X-ray
# of chest (procedure)"). Matching on the bare word wrongly routed
# every referral/imaging action into the "procedure" disposition.
_PROCEDURE_TOKENS = (
    "biopsy",
    "excision",
    "surgery",
    "operation",
    "oscopy",  # endoscopy, gastroscopy, colonoscopy, esophagogastroduodenoscopy...
    "resection",
)
_REFERRAL_TOKENS = (
    "referral",
    "refer using",
    "refer to",
    "refer people",
    "refer patients",
)
_CLINIC_TOKENS = ("clinic", "outpatient", "appointment", "review")


def disposition_label(code: str | None) -> str | None:
    if not code:
        return None
    return _DISPOSITION_LABELS.get(code, code.replace("_", " ").title())


def format_spoa_recommendation_markdown(
    disposition: str | None,
    evidence: str | None = None,
) -> str:
    """Render advisory SPoA disposition for the Recommendation section."""
    if not disposition:
        return ""
    label = disposition_label(disposition) or disposition.replace("_", " ").title()
    lines = [f"**Advisory SPoA disposition:** {label}."]
    if evidence:
        lines.append(f"_{evidence}_")
    return "\n".join(lines)


def prepend_spoa_disposition_to_recommendation(
    recommendation_md: str,
    disposition: str | None,
    evidence: str | None = None,
) -> str:
    """Prefix deterministic SPoA disposition onto Recommendation markdown."""
    prefix = format_spoa_recommendation_markdown(disposition, evidence)
    if not prefix:
        return recommendation_md
    body = (recommendation_md or "").strip()
    return f"{prefix}\n\n{body}" if body else prefix


def _rule_actions(rule: dict[str, Any]) -> list[dict[str, Any]]:
    actions = rule.get("actions")
    if isinstance(actions, list) and actions:
        return actions
    legacy = rule.get("action")
    return [legacy] if legacy else []


def _rule_priority(rule: dict[str, Any]) -> str | None:
    actions = _rule_actions(rule)
    if not actions:
        return None
    return str(actions[0].get("priority") or "").lower() or None


def _action_text(rule: dict[str, Any]) -> str:
    parts: list[str] = []
    for action in _rule_actions(rule):
        for key in ("name", "concept_name", "display"):
            value = str(action.get(key) or "").strip()
            if value:
                parts.append(value.lower())
    rec = str(rule.get("recommendation_verbatim") or "").lower()
    if rec:
        parts.append(rec)
    return " ".join(parts)


def _action_kind(rule: dict[str, Any]) -> str:
    text = _action_text(rule)
    # A referral routes the patient into a (fast-tracked) outpatient
    # pathway -- check this before the procedure tokens, since a
    # referral's SNOMED preferred term often carries the generic
    # "(procedure)" semantic tag too (referrals live under SNOMED's
    # procedure hierarchy) without meaning SPoA should book a direct
    # procedure.
    if any(token in text for token in _REFERRAL_TOKENS):
        return "outpatient_appointment"
    if any(token in text for token in _PROCEDURE_TOKENS):
        return "procedure"
    if any(token in text for token in _DIAGNOSTIC_TOKENS):
        return "straight_to_test"
    if any(token in text for token in _CLINIC_TOKENS):
        return "outpatient_appointment"
    if _rule_priority(rule) in _TIME_CRITICAL:
        return "straight_to_test"
    return "outpatient_appointment"


def _best_rule(rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rules:
        return None
    order = {"immediate": 0, "very_urgent": 1, "2ww": 2, "urgent": 3, "routine": 4}
    return sorted(
        rules,
        key=lambda rule: (
            order.get(_rule_priority(rule) or "routine", 9),
            -(rule.get("confidence") or 0.0),
            rule.get("name") or "",
        ),
    )[0]


def derive_spoa_disposition(
    *,
    primary_rules: list[dict[str, Any]],
    alternative_rules: list[dict[str, Any]],
    source_node_type: str | None = None,
    healthcare_service_spoa_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Return advisory disposition code and plain-English evidence string."""
    if primary_rules:
        best = _best_rule(primary_rules) or primary_rules[0]
        if str(source_node_type or "") == "CommunicationRequest":
            return (
                "discussion_with_primary_care",
                "Primary service guidelines matched; A&G request suggests advice to primary care.",
            )
        kind = _action_kind(best)
        rule_name = best.get("name") or best.get("rule_id") or "matched rule"
        return (
            kind,
            f"Receiving service guidelines matched: {rule_name}.",
        )

    if alternative_rules:
        best = _best_rule(alternative_rules) or alternative_rules[0]
        guideline = (
            best.get("guideline_title")
            or best.get("guideline_id")
            or "another guideline"
        )
        if healthcare_service_spoa_id:
            return (
                "next_internal_spoa",
                f"Receiving service guidelines did not match; {guideline} would support this request.",
            )
        return (
            "refer_to_alternative_service",
            f"Receiving service guidelines did not match; {guideline} would support this request.",
        )

    return None, None
