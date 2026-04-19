"""Deterministic Assessment narrative from /terminology/guidelines/evaluate.

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
      "action": {
        "priority": "2ww",          # "2ww" | "urgent" | "routine"
        "due_days": 14,
        "snomed_concept_id": "...",
        "name": "Chest X-ray request"
      },
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


TERMINOLOGY_API_URL = os.getenv(
    "TERMINOLOGY_API_URL", "http://localhost:8003"
).rstrip("/")
EVAL_TIMEOUT_S = float(os.getenv("SBAR_EVAL_TIMEOUT_S", "30"))


_PRIORITY_ORDER: dict[str, int] = {"2ww": 0, "urgent": 1, "routine": 2}
_PRIORITY_LABEL: dict[str, str] = {
    "2ww": "Two week wait (urgent suspected cancer)",
    "urgent": "Urgent",
    "routine": "Routine",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AssessmentNarrative:
    """Output of ``format_assessment``.

    ``markdown`` is human-readable Markdown that goes into
    ``Assessment.assessment``. ``rules`` and ``codes`` are the structured
    snapshots that get persisted alongside it for downstream consumers.
    """

    markdown: str
    rules: list[dict[str, Any]] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    pathway_hints: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_codes_against_guidelines(
    *,
    patient_codes: Iterable[str],
    guideline_ids: Iterable[str] | None = None,
    patient_age: float | None = None,
    patient_sex: str | None = None,
    timeout_s: float = EVAL_TIMEOUT_S,
) -> dict[str, Any]:
    """POST patient codes to the terminology API and return matched rules.

    When ``guideline_ids`` is empty, evaluates against the global scope.
    When one or more guideline ids are passed, makes one POST per
    guideline and merges the results (rule_id-deduped).
    """
    code_list = sorted({str(c).strip() for c in patient_codes if str(c).strip()})
    if not code_list:
        return {"matched_rules": [], "active_version": None, "scope": "none"}

    targets = list(guideline_ids or [])
    if not targets:
        targets = [None]

    merged: dict[str, dict[str, Any]] = {}
    active_version: str | None = None
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
        try:
            with httpx.Client(timeout=timeout_s) as http:
                resp = http.post(
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
) -> AssessmentNarrative:
    """Render matched rules into Markdown + structured snapshots.

    The Markdown begins with a one-line summary, then a section per
    priority (2WW, Urgent, Routine), then a 'No matches' fallback when
    nothing fires. Pathway hints (``stt`` / ``rtr`` / ``alternative``)
    are derived from the matched rules per DI-LEO-AI-189: STT is the
    minimum due-days across 2WW matches, RTR is set to "yes" when any
    2WW or urgent rule fires, and alternative_pathway lists rules whose
    strength is "conditional" or whose priority is "routine".
    """
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
            _PRIORITY_ORDER.get(((r.get("action") or {}).get("priority") or "routine"), 9),
            -(r.get("confidence") or 0.0),
            r.get("name") or "",
        ),
    )

    by_priority: dict[str, list[dict[str, Any]]] = {"2ww": [], "urgent": [], "routine": []}
    for rule in rules_sorted:
        prio = ((rule.get("action") or {}).get("priority") or "routine").lower()
        by_priority.setdefault(prio, []).append(rule)

    lines: list[str] = []
    lines.append(
        f"**{len(rules_sorted)} guideline rule(s) fired** "
        f"(scope: {'guidelines ' + ', '.join(guideline_ids) if guideline_ids else 'global'})."
    )

    for prio in ("2ww", "urgent", "routine"):
        bucket = by_priority.get(prio) or []
        if not bucket:
            continue
        lines.append("")
        lines.append(f"### {_PRIORITY_LABEL[prio]}")
        for rule in bucket:
            lines.append(_render_rule_bullet(rule))

    pathway_hints = _derive_pathway_hints(rules_sorted)

    return AssessmentNarrative(
        markdown="\n".join(lines),
        rules=[_rule_snapshot(r) for r in rules_sorted],
        codes=patient_codes,
        pathway_hints=pathway_hints,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _render_rule_bullet(rule: dict[str, Any]) -> str:
    title = (
        rule.get("name")
        or rule.get("guideline_title")
        or rule.get("rule_id")
        or "(unnamed rule)"
    )
    strength = (rule.get("strength") or "").strip()
    rec = (rule.get("recommendation_verbatim") or "").strip()
    action = rule.get("action") or {}
    due_days = action.get("due_days")
    action_name = (action.get("name") or "").strip()

    parts = [f"- **{title}**"]
    if strength:
        parts.append(f" _(strength: {strength})_")
    parts.append(f" -- rule `{rule.get('rule_id', '?')}`")
    out = "".join(parts)
    if rec:
        out += f"\n  - Recommendation: {rec}"
    matched_via_line = _render_matched_via(rule.get("matched_via"))
    if matched_via_line:
        out += f"\n  - Matched on: {matched_via_line}"
    if action_name:
        if due_days:
            out += f"\n  - Action: {action_name} (within {due_days} days)"
        else:
            out += f"\n  - Action: {action_name}"
    gid = rule.get("guideline_id")
    gtitle = rule.get("guideline_title")
    if gid or gtitle:
        out += f"\n  - Guideline: {gtitle or gid} (`{gid}`)"
    return out


def _render_matched_via(matched_via: list[dict[str, Any]] | None) -> str:
    """Render per-leaf hits as a short, plain-English line for SBAR.

    Implements UN-LEO-AI-093 acceptance criterion: name the matched code
    rather than only the rule. Output uses sentence case and short labels
    so the reading age stays at 9-11 (per `health-literacy.mdc`).

    Examples:
        - One leaf, one hit, exact match  -> "Smoker"
        - One leaf, one hit, descendant   -> "Cigarette smoker (a kind of Smoker)"
        - One leaf, two hits              -> "Cigarette smoker, Pipe smoker (kinds of Smoker)"
        - Two leaves                      -> "Smoker; History of asbestos exposure"
    """
    if not matched_via:
        return ""
    fragments: list[str] = []
    for entry in matched_via:
        hits = list(entry.get("matched_concept_ids") or [])
        if not hits:
            continue
        primary = entry.get("primary_concept_id")
        chip_label = (entry.get("preferred_term") or "").strip() or "matched code"
        # Best-effort: strip a trailing semantic-tag bracket for readability.
        if " (" in chip_label and chip_label.endswith(")"):
            chip_label = chip_label.rsplit(" (", 1)[0]
        if hits == [primary]:
            fragments.append(chip_label)
            continue
        if len(hits) == 1:
            fragments.append(f"`{hits[0]}` (a kind of {chip_label})")
        else:
            joined = ", ".join(f"`{h}`" for h in hits)
            fragments.append(f"{joined} (kinds of {chip_label})")
    return "; ".join(fragments)


def _rule_snapshot(rule: dict[str, Any]) -> dict[str, Any]:
    """Trim the rule payload to a JSON-serialisable snapshot.

    ``matched_via`` (DI-LEO-AI-510) is preserved so downstream renderers
    and audit tooling can show *which* synonym seed on the patient caused
    the rule to fire (e.g. "matched on Cigarette smoker (a kind of
    Smoker)") rather than only naming the rule.
    """
    snapshot = {
        "rule_id": rule.get("rule_id"),
        "name": rule.get("name"),
        "strength": rule.get("strength"),
        "guideline_id": rule.get("guideline_id"),
        "guideline_title": rule.get("guideline_title"),
        "chapter_title": rule.get("chapter_title"),
        "recommendation_verbatim": rule.get("recommendation_verbatim"),
        "action": rule.get("action"),
        "confidence": rule.get("confidence"),
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
    twoww = [r for r in rules if ((r.get("action") or {}).get("priority")) == "2ww"]
    urgent = [r for r in rules if ((r.get("action") or {}).get("priority")) == "urgent"]
    routine = [r for r in rules if ((r.get("action") or {}).get("priority")) == "routine"]
    conditional = [r for r in rules if (r.get("strength") or "").lower() == "conditional"]

    stt: str | None = None
    stt_evidence: str | None = None
    if twoww:
        due_days = [
            (r.get("action") or {}).get("due_days")
            for r in twoww
            if (r.get("action") or {}).get("due_days") is not None
        ]
        if due_days:
            stt = f"Within {min(due_days)} days (two-week wait)"
        else:
            stt = "Two-week wait"
        stt_evidence = "; ".join(r.get("rule_id", "?") for r in twoww[:3])

    rtr: str
    rtr_evidence: str
    if twoww or urgent:
        rtr = "yes"
        ids = [r.get("rule_id", "?") for r in (twoww + urgent)[:3]]
        rtr_evidence = f"Triggered by rule(s): {', '.join(ids)}"
    else:
        rtr = "no"
        rtr_evidence = (
            "No 2WW or urgent rule fired; routine review applies"
            if routine
            else "No matching rules fired"
        )

    alt: str | None = None
    alt_evidence: str | None = None
    candidates = conditional + routine
    if candidates:
        names = [
            (r.get("name") or r.get("rule_id") or "?")
            for r in candidates[:3]
        ]
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
