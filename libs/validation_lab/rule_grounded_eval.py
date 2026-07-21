"""Deterministic expectedTrigger via GuidelineEvaluator.

Atlas trace:
  DO: DO-A0ADDB38
  DI: DI-EB716E68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")

Atlas: DI-EB716E68 / DO-A0ADDB38

expectedTrigger is non-null only when a rule_id is attached AND that rule
is present in the currently loaded compiled ruleset. A missing/uncompiled
rule is never treated as False.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _make_evaluator() -> Any:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    return GuidelineEvaluator()


def _codes_from_variant(variant: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for row in variant.get("pmh") or []:
        if isinstance(row, dict):
            cid = str(row.get("conceptId") or row.get("concept_id") or "").strip()
            if cid and cid not in codes:
                codes.append(cid)
    for cid in variant.get("triggerConceptIds") or []:
        cleaned = str(cid).strip()
        if cleaned and cleaned not in codes:
            codes.append(cleaned)
    return codes


def _observations_from_variant(variant: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for row in variant.get("observations") or []:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("observableId") or row.get("observable_id") or "").strip()
        if not oid:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        unit = str(row.get("unit") or "").strip()
        if not unit:
            continue
        out.append(
            {
                "observable_id": oid,
                "value": value,
                "unit": unit,
                "observed_at": str(row.get("observed_at") or now),
            }
        )
    return out


def _age_from_variant(variant: dict[str, Any]) -> float | None:
    raw = variant.get("patientAge")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _ruleset_contains_rule(evaluator: Any, rule_id: str) -> bool:
    """Return True when rule_id is in the evaluator's loaded active ruleset."""
    try:
        ruleset = evaluator._load_ruleset(None, None, None)
    except Exception:
        logger.warning("Could not load ruleset for rule %s", rule_id, exc_info=True)
        return False
    if not ruleset:
        return False
    target = str(rule_id).strip()
    for rule in ruleset.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("rule_id") or rule.get("id") or "").strip()
        if rid == target:
            return True
    return False


def evaluate_variant_against_rule(
    rule_id: str | None,
    variant: dict[str, Any],
) -> tuple[bool | None, str]:
    """Return (expected_trigger, reason) for a variant vs a compiled rule.

    reason is one of:
      - "no recommendation attached"
      - "rule not currently compiled"
      - "verified"
    """
    cleaned_rule = str(rule_id or "").strip()
    if not cleaned_rule:
        return None, "no recommendation attached"

    evaluator = _make_evaluator()
    if not _ruleset_contains_rule(evaluator, cleaned_rule):
        return None, "rule not currently compiled"

    age = _age_from_variant(variant)
    sex = str(variant.get("patientSex") or "").strip() or None
    codes = _codes_from_variant(variant)
    observations = _observations_from_variant(variant)
    result = evaluator.evaluate_patient(
        codes,
        patient_age=age,
        patient_sex=sex,
        patient_observations=observations or None,
    )
    matched = result.get("matched_rules") or []
    matched_ids = {
        str(m.get("rule_id") or m.get("id") or "").strip()
        for m in matched
        if isinstance(m, dict)
    }
    return (cleaned_rule in matched_ids), "verified"
