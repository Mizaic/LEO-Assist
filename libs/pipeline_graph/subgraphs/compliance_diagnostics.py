"""Validation Lab compliance trace helpers (stage summary + guideline diagnostics).

Atlas trace:
  DI: DI-FE423B8D
  DO: DO-158BE606
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-FE423B8D")

Only populated when ``capture_validation_output`` is true on pipeline state.
"""

from __future__ import annotations

from typing import Any

_MAX_MATCHED_DIAGNOSTICS = 5
_MAX_NEAR_MISS = 3
_MAX_NEAR_MISS_CANDIDATES = 40
_MAX_CODES_IN_SUMMARY = 24


def _entity_code_entries(entities: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for index, entity in enumerate(entities):
        concept_id = entity.get("concept_id") or entity.get("snomed_concept_id")
        if not concept_id and isinstance(entity.get("coding"), dict):
            concept_id = entity["coding"].get("snomed_concept_id")
        code = str(concept_id or "").strip()
        if not code:
            continue
        text = str(entity.get("text") or entity.get("concept_name") or "").strip()
        entries.append(
            {
                "concept_id": code,
                "entity_index": str(index),
                "text": text[:120],
            }
        )
    return entries


def _tree_leaf_counts(node: dict[str, Any] | None) -> tuple[int, int]:
    """Return (matched_leaves, total_leaves) for an annotated logic tree."""
    if not node:
        return 0, 0
    children = node.get("children")
    if isinstance(children, list) and children:
        matched = 0
        total = 0
        for child in children:
            if not isinstance(child, dict):
                continue
            cm, ct = _tree_leaf_counts(child)
            matched += cm
            total += ct
        if total:
            return matched, total
    if "matched" in node:
        return (1, 1) if bool(node.get("matched")) else (0, 1)
    return 0, 0


def _compact_diagnostic(diag: dict[str, Any]) -> dict[str, Any]:
    tree = diag.get("annotated_tree")
    matched_leaves, total_leaves = _tree_leaf_counts(
        tree if isinstance(tree, dict) else None
    )
    ratio = round(matched_leaves / total_leaves, 3) if total_leaves else 0.0
    return {
        "rule_id": str(diag.get("rule_id") or ""),
        "rule_name": str(diag.get("rule_name") or ""),
        "guideline_id": str(diag.get("guideline_id") or ""),
        "fires": bool(diag.get("fires")),
        "match_ratio": ratio,
        "matched_leaves": matched_leaves,
        "total_leaves": total_leaves,
        "annotated_tree": tree,
    }


def build_stage_summary(
    state: dict[str, Any],
    *,
    codes: list[str],
    entities: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Human-readable compliance stage summary for Run Inspector."""
    scope_type = str(state.get("guideline_scope_type") or "guideline")
    scope_id = str(state.get("guideline_scope_id") or state.get("guideline_id") or "")
    matched = list(result.get("matched_rules") or [])
    matched_ids = [str(rule.get("rule_id") or rule.get("id") or "") for rule in matched]
    matched_ids = [rid for rid in matched_ids if rid]
    code_entries = _entity_code_entries(entities)
    shown_codes = codes[:_MAX_CODES_IN_SUMMARY]
    headline = (
        f"{len(matched)} rule(s) matched on {scope_id or 'guideline'}"
        if matched
        else f"No rules matched on {scope_id or 'guideline'}"
    )
    return {
        "subgraph_id": "compliance",
        "headline": headline,
        "inputs": {
            "guideline_scope_type": scope_type,
            "guideline_scope_id": scope_id,
            "ruleset_version": str(
                result.get("ruleset_version")
                or state.get("guideline_ruleset_version")
                or result.get("active_version")
                or ""
            ),
            "active_version": str(result.get("active_version") or ""),
            "patient_code_count": len(codes),
            "evaluated_codes": shown_codes,
            "evaluated_codes_truncated": len(codes) > len(shown_codes),
            "patient_age": state.get("patient_age"),
            "patient_sex": state.get("patient_sex"),
            "code_sources": code_entries[:_MAX_CODES_IN_SUMMARY],
        },
        "outputs": {
            "matched_rule_count": len(matched),
            "matched_rule_ids": matched_ids,
            "is_compliant": bool(result.get("is_compliant")),
            "gender_review_flag": bool(result.get("gender_review_flag")),
            "gender_sensitive_rules_skipped": int(
                result.get("gender_sensitive_rules_skipped") or 0
            ),
            "not_compiled": bool(result.get("not_compiled")),
        },
        "warnings": [],
    }


def build_guideline_diagnostics(
    evaluator: Any,
    state: dict[str, Any],
    *,
    codes: list[str],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Run diagnose() for matched rules and top near-miss rules (Lab only)."""
    if not state.get("capture_validation_output"):
        return {}

    scope_type = str(state.get("guideline_scope_type") or "guideline")
    scope_id = str(state.get("guideline_scope_id") or state.get("guideline_id") or "")
    ruleset_version = state.get("guideline_ruleset_version") or None
    observations = state.get("patient_observations")
    active_medications = list(state.get("active_medications") or [])
    allergies = list(state.get("allergies") or [])
    treatment_history = list(state.get("treatment_history") or [])
    diag_kwargs = {
        "patient_age": state.get("patient_age"),
        "patient_sex": state.get("patient_sex"),
        "scope_type": scope_type if scope_id else None,
        "scope_id": scope_id or None,
        "ruleset_version": ruleset_version,
        "patient_observations": observations,
        "active_medications": active_medications or None,
        "allergies": allergies or None,
        "treatment_history": treatment_history or None,
    }

    matched_rules = list(result.get("matched_rules") or [])
    matched_stems = {
        str(rule.get("rule_id") or rule.get("id") or "") for rule in matched_rules
    }
    matched_stems = {s for s in matched_stems if s}

    matched_diag: list[dict[str, Any]] = []
    for rule in matched_rules[:_MAX_MATCHED_DIAGNOSTICS]:
        rule_id = str(rule.get("rule_id") or rule.get("id") or "")
        if not rule_id:
            continue
        diag = evaluator.diagnose(rule_id, codes, **diag_kwargs)
        if isinstance(diag, dict):
            matched_diag.append(_compact_diagnostic(diag))

    near_miss: list[dict[str, Any]] = []
    ruleset = evaluator._load_ruleset(ruleset_version, scope_type, scope_id)
    if ruleset:
        candidates: list[tuple[float, dict[str, Any]]] = []
        for rule in (ruleset.get("rules") or [])[:_MAX_NEAR_MISS_CANDIDATES]:
            rule_id = str(rule.get("rule_id") or "")
            if not rule_id or rule_id in matched_stems:
                continue
            if scope_id and rule.get("guideline_id") != scope_id:
                continue
            diag = evaluator.diagnose(rule_id, codes, **diag_kwargs)
            if not isinstance(diag, dict) or diag.get("fires"):
                continue
            compact = _compact_diagnostic(diag)
            ratio = float(compact.get("match_ratio") or 0.0)
            if ratio <= 0.0:
                continue
            candidates.append((ratio, compact))
        candidates.sort(key=lambda item: item[0], reverse=True)
        near_miss = [item[1] for item in candidates[:_MAX_NEAR_MISS]]

    return {
        "matched": matched_diag,
        "near_miss": near_miss,
        "scope_type": scope_type,
        "scope_id": scope_id,
    }
