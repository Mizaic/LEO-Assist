"""Deterministic Assessment narrative from /terminology/guidelines/evaluate.

Atlas trace:
  DO: DO-B226E498
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B226E498")

V1 deliberately avoids LLM interpretation of the matched rules. The
Assessment section presents matched rules verbatim with structured
attribution so the clinician can see exactly which guideline fired and
why. See DI-LEO-AI-189.

The roaring-bitmap evaluator returns ``matched_rules`` shaped like::

    {
      "rule_id": "...",
      "name": "...",
      "strength": "strong",
      "guideline_id": "G-...",
      "guideline_title": "Suspected lung cancer",
      "chapter_title": "Referral criteria",
      "recommendation_verbatim": "Refer for chest X-ray within 2 weeks",
      "actions": [
        {
          "priority": "2ww",  # immediate | very_urgent | 2ww | urgent | routine
                                       # across every action on a rule
          "due_days": 14,
          "concept_id": "...",
          "name": "Chest X-ray request",
          "strength": "offer"
        },
        ...
      ],
      # "action" (actions[0], or None when empty) is kept for one release
      # as a read-only back-compat field -- see guideline_compiler.py.
      "action": {...},
      "confidence": 1.0
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx
import logging
import os

logger = logging.getLogger(__name__)


TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8003").rstrip(
    "/"
)
EVAL_TIMEOUT_S = float(os.getenv("SBAR_EVAL_TIMEOUT_S", "30"))


_PRIORITY_ORDER: dict[str, int] = {
    "immediate": 0,
    "very_urgent": 1,
    "2ww": 2,
    "urgent": 3,
    "routine": 4,
}
_PRIORITY_LABEL: dict[str, str] = {
    "immediate": "Immediate specialist assessment",
    "very_urgent": "Very urgent (within 48 hours)",
    "2ww": "Two week wait (urgent suspected cancer)",
    "urgent": "Urgent",
    "routine": "Routine",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AssessmentNarrative:
    """Output of ``format_assessment``."""

    markdown: str
    rules: list[dict[str, Any]] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    pathway_hints: dict[str, Any] = field(default_factory=dict)
    spoa_disposition: str | None = None
    spoa_disposition_evidence: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def evaluate_codes_against_guidelines(
    *,
    patient_codes: Iterable[str],
    guideline_ids: Iterable[str] | None = None,
    patient_age: float | None = None,
    patient_sex: str | None = None,
    observations: list[dict[str, Any]] | None = None,
    active_medications: list[dict[str, Any]] | None = None,
    allergies: list[dict[str, Any]] | None = None,
    treatment_history: list[dict[str, Any]] | None = None,
    timeout_s: float = EVAL_TIMEOUT_S,
) -> dict[str, Any]:
    """POST patient codes to the terminology API and return matched rules.

    When ``guideline_ids`` is empty, evaluates against the global scope.
    When one or more guideline ids are passed, makes one POST per
    guideline and merges the results (rule_id-deduped).

    A single AsyncClient is reused across all per-guideline requests so
    the underlying TCP connection is kept warm.

    Sprint 1: ``observations``, ``active_medications``, ``allergies``, and
    ``treatment_history`` are passed through to the evaluate endpoint when
    provided. This ensures the SBAR formatter and the evaluator use the
    same fact inputs (DI-2687230E / DI-2199E670).
    """
    code_list = sorted({str(c).strip() for c in patient_codes if str(c).strip()})
    if not code_list:
        return {"matched_rules": [], "active_version": None, "scope": "none"}

    targets = list(guideline_ids or [])
    if not targets:
        targets = [None]

    merged: dict[str, dict[str, Any]] = {}
    active_version: str | None = None
    async with httpx.AsyncClient(timeout=timeout_s) as http:
        for gid in targets:
            body: dict[str, Any] = {
                "patient_codes": code_list,
                "scope_type": "guideline" if gid else "global",
                "scope_id": gid or "default",
            }
            if patient_age is not None:
                body["patient_age"] = patient_age
            if patient_sex:
                body["patient_sex"] = patient_sex
            if observations:
                body["observations"] = observations
            if active_medications:
                body["active_medications"] = active_medications
            if allergies:
                body["allergies"] = allergies
            if treatment_history:
                body["treatment_history"] = treatment_history
            try:
                resp = await http.post(
                    f"{TERMINOLOGY_API_URL}/terminology/guidelines/evaluate",
                    json=body,
                )
                resp.raise_for_status()
                payload = resp.json()
            except httpx.HTTPError as exc:
                logger.warning(
                    "evaluate_codes_against_guidelines: %s for guideline=%s",
                    exc,
                    gid or "global",
                )
                continue
            active_version = payload.get("active_version") or active_version
            for rule in payload.get("matched_rules") or []:
                rid = rule.get("rule_id")
                if not rid or rid in merged:
                    continue
                merged[rid] = rule

    return {
        "matched_rules": list(merged.values()),
        "active_version": active_version,
        "scope": "guideline" if (guideline_ids or []) else "global",
    }


def format_assessment(
    *,
    matched_rules: list[dict[str, Any]],
    patient_codes: list[str],
    guideline_ids: list[str] | None = None,
    compliance_context: dict[str, Any] | None = None,
    spoa_disposition: str | None = None,
    spoa_disposition_evidence: str | None = None,
) -> AssessmentNarrative:
    """Render matched rules into Markdown + structured snapshots."""
    if compliance_context:
        return _format_spoa_assessment(
            matched_rules=matched_rules,
            patient_codes=patient_codes,
            guideline_ids=guideline_ids,
            compliance_context=compliance_context,
            spoa_disposition=spoa_disposition,
            spoa_disposition_evidence=spoa_disposition_evidence,
        )

    if not matched_rules:
        return AssessmentNarrative(
            markdown=(
                "_No matching guideline rules fired for this patient's coded "
                "evidence._\n\nReviewed against "
                f"{len(patient_codes)} SNOMED concept(s)."
            ),
            rules=[],
            codes=patient_codes,
            pathway_hints={
                "stt": None,
                "stt_evidence": None,
                "alternative_pathway": None,
                "alternative_pathway_evidence": None,
                "rtr": "no",
                "rtr_evidence": "No matching rules fired",
            },
        )

    rules_sorted = sorted(
        matched_rules,
        key=lambda r: (
            _PRIORITY_ORDER.get(_rule_raw_priority(r) or "routine", 9),
            -(r.get("confidence") or 0.0),
            r.get("name") or "",
        ),
    )

    by_priority: dict[str, list[dict[str, Any]]] = {
        "immediate": [],
        "very_urgent": [],
        "2ww": [],
        "urgent": [],
        "routine": [],
    }
    for rule in rules_sorted:
        prio = (_rule_raw_priority(rule) or "routine").lower()
        by_priority.setdefault(prio, []).append(rule)

    lines: list[str] = []
    scope = "guidelines " + ", ".join(guideline_ids) if guideline_ids else "global"
    lines.append(f"**{len(rules_sorted)} guideline rule(s) fired** (scope: {scope}).")

    for prio in ("immediate", "very_urgent", "2ww", "urgent", "routine"):
        bucket = by_priority.get(prio) or []
        if not bucket:
            continue
        lines.append("")
        lines.append(f"### {_PRIORITY_LABEL.get(prio, prio)}")
        for rule in bucket:
            lines.append(_render_rule_bullet(rule))

    pathway_hints = _derive_pathway_hints(rules_sorted)

    return AssessmentNarrative(
        markdown="\n".join(lines),
        rules=[_rule_snapshot(r) for r in rules_sorted],
        codes=patient_codes,
        pathway_hints=pathway_hints,
        spoa_disposition=spoa_disposition,
        spoa_disposition_evidence=spoa_disposition_evidence,
    )


def _format_spoa_assessment(
    *,
    matched_rules: list[dict[str, Any]],
    patient_codes: list[str],
    guideline_ids: list[str] | None,
    compliance_context: dict[str, Any],
    spoa_disposition: str | None,
    spoa_disposition_evidence: str | None,
) -> AssessmentNarrative:
    primary = dict(compliance_context.get("primary") or {})
    alternatives = dict(compliance_context.get("alternatives") or {})
    primary_rules = list(primary.get("matched_rules") or matched_rules or [])
    alternative_rules = list(alternatives.get("matched_rules") or [])
    service_name = str(primary.get("service_name") or "").strip()
    service_specialty = str(primary.get("service_specialty") or "").strip()
    primary_ids = list(primary.get("guideline_ids") or guideline_ids or [])
    supported = bool(primary.get("supported"))
    ruleset_missing = bool(primary.get("ruleset_missing")) or (
        bool(compliance_context.get("degraded")) and not supported
    )

    lines: list[str] = []
    if service_name:
        scope = f"{service_name}"
        if service_specialty:
            scope += f" ({service_specialty})"
        if primary_ids:
            scope += f" -- guidelines {', '.join(primary_ids)}"
        lines.append(f"**Receiving service:** {scope}.")
    elif compliance_context.get("healthcare_service_missing"):
        lines.append(
            "_Receiving service is not linked; guideline scope may be incomplete._"
        )

    lines.extend(
        _receiving_support_lines(
            supported=supported,
            ruleset_missing=ruleset_missing,
            primary_rules=primary_rules,
            patient_codes=patient_codes,
        )
    )

    if alternative_rules:
        lines.append("")
        lines.append("**Other guidelines that would support this request**")
        for rule in alternative_rules[:5]:
            lines.append(_render_rule_bullet(rule))

    rules_for_hints = primary_rules or alternative_rules
    pathway_hints = (
        _derive_pathway_hints(rules_for_hints)
        if rules_for_hints
        else {
            "stt": None,
            "stt_evidence": None,
            "alternative_pathway": None,
            "alternative_pathway_evidence": None,
            "rtr": "no",
            "rtr_evidence": "No matching rules fired",
        }
    )
    all_rules = _dedupe_rules_by_id(primary_rules + alternative_rules)
    return AssessmentNarrative(
        markdown="\n".join(lines),
        rules=[_rule_snapshot(r) for r in all_rules],
        codes=patient_codes,
        pathway_hints=pathway_hints,
        spoa_disposition=spoa_disposition,
        spoa_disposition_evidence=spoa_disposition_evidence,
    )


def _receiving_support_lines(
    *,
    supported: bool,
    ruleset_missing: bool,
    primary_rules: list[dict[str, Any]],
    patient_codes: list[str],
) -> list[str]:
    if ruleset_missing:
        return [
            "We could not check the receiving service ruleset.",
            "A person needs to review this referral.",
        ]
    if supported:
        lines = ["**Supported by receiving service?** yes."]
        lines.extend(_render_rule_section("Primary matches", primary_rules))
        return lines
    return [
        "**Supported by receiving service?** no.",
        (
            "_No matching guideline rules fired for this patient's coded evidence "
            "against the receiving service scope._"
        ),
        f"Reviewed against {len(patient_codes)} SNOMED concept(s).",
    ]


def _render_rule_section(title: str, rules: list[dict[str, Any]]) -> list[str]:
    if not rules:
        return []
    lines = ["", f"**{title}**"]
    for rule in rules:
        lines.append(_render_rule_bullet(rule))
    return lines


def _dedupe_rules_by_id(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "").strip()
        if not rule_id or rule_id in merged:
            continue
        merged[rule_id] = rule
    return list(merged.values())


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _rule_actions(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a rule's actions as a list, tolerating the legacy singular shape.

    Prefers ``rule["actions"]`` (the multi-action shape emitted by
    ``guideline_evaluator._format_match``). Falls back to a 1-item list
    built from the legacy ``rule["action"]`` dict so callers/fixtures that
    only supply the singular field keep working unchanged.
    """
    actions = rule.get("actions")
    if isinstance(actions, list) and actions:
        return actions
    legacy = rule.get("action")
    return [legacy] if legacy else []


def _rule_raw_priority(rule: dict[str, Any]) -> str | None:
    """Return a rule's priority without defaulting (None when no action).

    Priority is rule-level (derived from the NICE recommendation's
    urgency), so every action on a rule carries the same value -- reading
    the first action is sufficient.
    """
    actions = _rule_actions(rule)
    return actions[0].get("priority") if actions else None


def _rule_due_days(rule: dict[str, Any]) -> Any:
    """Return a rule's due_days without defaulting (None when no action)."""
    actions = _rule_actions(rule)
    return actions[0].get("due_days") if actions else None


def _render_action_lines(rule: dict[str, Any]) -> list[str]:
    """Return one '**Action:** ...' line per recommended action on a rule."""
    from libs.guidance.narrative_actions import display_action_label

    lines: list[str] = []
    for action in _rule_actions(rule):
        name = display_action_label(action)
        if not name:
            continue
        due_days = action.get("due_days")
        if due_days:
            lines.append(f"**Action:** {name} (within {due_days} days)")
        else:
            lines.append(f"**Action:** {name}")
    return lines


def _render_guideline_line(rule: dict[str, Any]) -> str | None:
    """Return a bold Guideline landmark with author, title, and code.

    Example: ``**Guideline:** NICE Suspected cancer: recognition and referral (`NG12`)``
    """
    from libs.guidance.guideline_attribution import format_guideline_attribution

    return format_guideline_attribution(
        guideline_id=rule.get("guideline_id") or "",
        guideline_title=rule.get("guideline_title") or "",
        guideline_author=rule.get("guideline_author"),
        guideline_publisher=rule.get("guideline_publisher"),
        guideline_source=rule.get("guideline_source"),
    )


def _render_rule_bullet(rule: dict[str, Any]) -> str:
    title = (
        rule.get("name")
        or rule.get("guideline_title")
        or rule.get("rule_id")
        or "(unnamed rule)"
    )
    strength = (rule.get("strength") or "").strip()
    rec = (rule.get("recommendation_verbatim") or "").strip()

    parts = [f"- **{title}**"]
    if strength:
        parts.append(f" _(strength: {strength})_")
    out = "".join(parts)
    if rec:
        out += f"\n  - **Recommendation:** {rec}"
    matched_via_line = _render_matched_via(rule.get("matched_via"))
    if matched_via_line:
        out += f"\n  - **Matched on:** {matched_via_line}"
    for action_line in _render_action_lines(rule):
        out += f"\n  - {action_line}"
    guideline_line = _render_guideline_line(rule)
    if guideline_line:
        out += f"\n  - {guideline_line}"
    return out


def _chip_label(entry: dict[str, Any]) -> str:
    """Return a short preferred-term label for a matched_via entry."""
    chip_label = (entry.get("preferred_term") or "").strip() or "matched code"
    # Best-effort: strip a trailing semantic-tag bracket for readability.
    if " (" in chip_label and chip_label.endswith(")"):
        return chip_label.rsplit(" (", 1)[0]
    return chip_label


def _format_age_years(value: float | int | None) -> str:
    if value is None:
        return ""
    rounded = int(value) if float(value).is_integer() else round(float(value), 1)
    return str(rounded)


def _demographic_matched_via_fragment(entry: dict[str, Any]) -> str | None:
    field = str(entry.get("field") or "").lower()
    if field == "age":
        patient_age = entry.get("patient_value")
        if patient_age is None:
            return None
        operator = str(entry.get("operator") or ">=").strip()
        threshold = entry.get("value")
        age_text = _format_age_years(patient_age)
        if operator == ">=" and threshold is not None:
            return f"Age {age_text} years ({_format_age_years(threshold)} or over)"
        if operator == ">" and threshold is not None:
            return f"Age {age_text} years (over {_format_age_years(threshold)})"
        if operator == "between" and isinstance(threshold, (list, tuple)):
            low = _format_age_years(threshold[0])
            high = _format_age_years(threshold[1])
            return f"Age {age_text} years ({low} to {high} years)"
        return f"Age {age_text} years"
    if field == "sex":
        patient_sex = str(entry.get("patient_value") or "").strip().lower()
        if not patient_sex:
            return None
        label = {"male": "male", "female": "female"}.get(patient_sex, patient_sex)
        return f"Gender recorded as {label}"
    return None


def _observation_matched_via_fragment(entry: dict[str, Any]) -> str | None:
    term = str(entry.get("observable_term") or "").strip()
    if not term:
        return None
    operator = str(entry.get("operator") or "").strip()
    value = entry.get("value")
    unit = str(entry.get("unit") or "").strip()
    if operator and value is not None:
        suffix = f" {unit}" if unit else ""
        return f"{term} {operator} {value}{suffix}"
    return term


def _label_matched_via_fragment(entry: dict[str, Any], fallback: str) -> str | None:
    label = str(entry.get("term") or entry.get("display_name") or "").strip()
    return label or fallback


def _matched_via_fragment(entry: dict[str, Any]) -> str | None:
    """Render one matched_via leaf as a short display fragment, or None."""
    kind = str(entry.get("kind") or "").upper()
    if kind == "DEMOGRAPHIC":
        return _demographic_matched_via_fragment(entry)
    if kind == "OBSERVATION":
        return _observation_matched_via_fragment(entry)
    if kind == "MEDICATION":
        return _label_matched_via_fragment(entry, "Active medication matched")
    if kind == "ALLERGY":
        return _label_matched_via_fragment(entry, "Allergy matched")
    if kind == "TREATMENT_HISTORY":
        return _label_matched_via_fragment(entry, "Treatment history matched")
    if kind == "RULE_FIRED":
        return _label_matched_via_fragment(entry, "Linked rule matched")
    hits = list(entry.get("matched_concept_ids") or [])
    if not hits:
        return None
    primary = entry.get("primary_concept_id")
    chip_label = _chip_label(entry)
    if hits == [primary]:
        return chip_label
    # A trailing qualifier (rather than a leading "a related coded
    # finding for ..." clause) reads more naturally when several
    # leaves are joined with "; " in one "Matched on:" line, and
    # avoids repeating the same clause for every leaf.
    if len(hits) == 1:
        return f"{chip_label} (related finding)"
    return f"{chip_label} (related findings)"


def _render_matched_via(matched_via: list[dict[str, Any]] | None) -> str:
    """Render per-leaf hits as a short, plain-English line for SBAR.

    Implements UN-LEO-AI-093 acceptance criterion: name every satisfied leaf on
    so the reading age stays at 9-11 (per `health-literacy.mdc`).

    Duplicate leaf labels are collapsed (same concept chip appearing more
    than once in an OR tree) so clinicians see each distinct match once.
    The full ``matched_via`` list is still kept on the rule snapshot for
    audit.

    Examples:
        - Age gate                        -> "Age 71 years (50 or over)"
        - Sex gate                        -> "Gender recorded as female"
        - One leaf, one hit, exact match  -> "Smoker"
        - One leaf, one hit, descendant   -> "Smoker (related finding)"
        - One leaf, many hits, descendant -> "Smoker (related findings)"
        - Two distinct leaves             -> "Smoker; History of asbestos exposure"
        - Three identical leaf labels     -> "Weight decreased"
    """
    if not matched_via:
        return ""
    fragments: list[str] = []
    seen: set[str] = set()
    for entry in matched_via:
        fragment = _matched_via_fragment(entry)
        if not fragment or fragment in seen:
            continue
        seen.add(fragment)
        fragments.append(fragment)
    return "; ".join(fragments)


# Strength hierarchy for deterministic bullet-1 selection (lower = higher
# priority). "refer" > "offer" > "consider". Unknown values sort last.
STRENGTH_RANK: dict[str, int] = {"refer": 0, "offer": 1, "consider": 2}


def _rule_snapshot(rule: dict[str, Any]) -> dict[str, Any]:
    """Trim the rule payload to a JSON-serialisable snapshot.

    ``name`` and ``strength`` are included so the widget "Matched
    guidelines" panel can display them and the recommendation LLM can
    use ``name`` in bullet-1 citations.  ``recommendation_verbatim``
    and ``action.name`` remain excluded -- they are verbose source text
    that cause the model to anchor and paraphrase rather than distil.

    ``matched_via`` (DI-LEO-AI-510) is preserved so downstream renderers
    and audit tooling can show which synonym seed caused the rule to fire.

    ``action`` (singular) keeps its historical priority/due_days-only shape
    for back-compat with ``prompt_calls.py``'s bullet-1 selection, since
    priority/due_days are rule-level and identical across every action.
    """
    actions = _rule_actions(rule)
    first_action = actions[0] if actions else {}
    snapshot: dict[str, Any] = {
        "rule_id": rule.get("rule_id"),
        "name": rule.get("name"),
        "strength": rule.get("strength"),
        "guideline_id": rule.get("guideline_id"),
        "guideline_title": rule.get("guideline_title"),
        "chapter_title": rule.get("chapter_title"),
        "action": {
            "priority": first_action.get("priority"),
            "due_days": first_action.get("due_days"),
        },
    }
    matched_via = rule.get("matched_via")
    if matched_via:
        snapshot["matched_via"] = list(matched_via)
    return snapshot


def _derive_pathway_hints(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute STT / RTR / alternative_pathway from matched rules.

    These are deliberately not LLM-generated -- they are deterministic
    summaries of the rule output so reviewers can audit them. See
    DI-LEO-AI-189 for the mapping rules.
    """
    immediate = [r for r in rules if _rule_raw_priority(r) == "immediate"]
    very_urgent = [r for r in rules if _rule_raw_priority(r) == "very_urgent"]
    twoww = [r for r in rules if _rule_raw_priority(r) == "2ww"]
    urgent = [r for r in rules if _rule_raw_priority(r) == "urgent"]
    routine = [r for r in rules if _rule_raw_priority(r) == "routine"]
    conditional = [
        r for r in rules if (r.get("strength") or "").lower() == "conditional"
    ]
    time_critical = immediate + very_urgent + twoww + urgent

    stt: str | None = None
    stt_evidence: str | None = None
    if immediate:
        stt = "Immediate specialist assessment"
        stt_evidence = "; ".join(r.get("rule_id", "?") for r in immediate[:3])
    elif very_urgent:
        due_days = [
            _rule_due_days(r) for r in very_urgent if _rule_due_days(r) is not None
        ]
        stt = (
            f"Within {min(due_days)} days (very urgent)"
            if due_days
            else "Very urgent (within 48 hours)"
        )
        stt_evidence = "; ".join(r.get("rule_id", "?") for r in very_urgent[:3])
    elif twoww:
        due_days = [_rule_due_days(r) for r in twoww if _rule_due_days(r) is not None]
        if due_days:
            stt = f"Within {min(due_days)} days (two-week wait)"
        else:
            stt = "Two-week wait"
        stt_evidence = "; ".join(r.get("rule_id", "?") for r in twoww[:3])

    rtr: str
    rtr_evidence: str
    if time_critical:
        rtr = "yes"
        ids = [r.get("rule_id", "?") for r in time_critical[:3]]
        rtr_evidence = f"Triggered by rule(s): {', '.join(ids)}"
    else:
        rtr = "no"
        rtr_evidence = (
            "No time-critical rule fired; routine review applies"
            if routine
            else "No matching rules fired"
        )

    alt: str | None = None
    alt_evidence: str | None = None
    candidates = conditional + routine
    if candidates:
        names = [(r.get("name") or r.get("rule_id") or "?") for r in candidates[:3]]
        alt = "; ".join(names)
        alt_evidence = "; ".join(r.get("rule_id", "?") for r in candidates[:3])

    return {
        "stt": stt,
        "stt_evidence": stt_evidence,
        "alternative_pathway": alt,
        "alternative_pathway_evidence": alt_evidence,
        "rtr": rtr,
        "rtr_evidence": rtr_evidence,
    }
