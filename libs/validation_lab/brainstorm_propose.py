"""Propose-variants phase for Validation Lab brainstorm.

Atlas trace:
  DO: DO-A0ADDB38
  DI: DI-EB716E68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")

Atlas: DI-EB716E68 / DO-A0ADDB38
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.prompts.validation_lab_brainstorm_v1 import (
    PROPOSE_TOOL_CONFIG,
    PROPOSE_VARIANTS_TOOL,
)
from libs.validation_lab.scenario_patch import (
    MAX_BRAINSTORM_RECOMMENDATIONS,
    VARIANTS_PER_RECOMMENDATION,
    normalise_variants,
    verify_patch,
)

logger = logging.getLogger(__name__)


def _too_many_recs_message(count: int) -> str:
    return (
        f"Too many recommendations attached ({count}). "
        f"Brainstorm can use at most {MAX_BRAINSTORM_RECOMMENDATIONS} "
        "at a time (about 3 test cases each). Remove some, or use "
        "Select all compiled on a smaller guideline chapter, then try again."
    )


def _forced_propose_tool_config() -> dict[str, Any]:
    return {
        "tools": [PROPOSE_VARIANTS_TOOL],
        "toolChoice": {"tool": {"name": "propose_variants"}},
    }


def _propose_once(
    *,
    user_payload: dict[str, Any],
    agent_task: str,
    variants_requested: int,
) -> dict[str, Any]:
    """Run propose tool loop once, with forced retry if empty."""
    # Late import so tests can monkeypatch brainstorm._run_tool_loop.
    from libs.validation_lab import brainstorm as core

    messages = [{"role": "user", "content": json.dumps(user_payload)}]
    result = core._run_tool_loop(
        messages=messages,
        tool_config=PROPOSE_TOOL_CONFIG,
        agent_task=agent_task,
        max_tokens=4096,
    )
    if result.get("proposed"):
        return result
    logger.warning("brainstorm.propose empty; retrying with forced toolChoice")
    nudge = (
        f"You must call propose_variants now with {variants_requested} "
        "trigger-positive variants based on scenario_text, answers, and "
        "recommendations. Do not reply with prose only."
    )
    return core._run_tool_loop(
        messages=[*messages, {"role": "user", "content": nudge}],
        tool_config=_forced_propose_tool_config(),
        agent_task=f"{agent_task}_retry",
        max_tokens=4096,
    )


def _stamp_target_rec(
    rows: list[dict[str, Any]],
    *,
    rec_id: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        if not str(item.get("targetRecId") or item.get("target_rec_id") or "").strip():
            item["targetRecId"] = rec_id
        out.append(item)
    return out


def _stamp_expected_trigger(
    variants: list[dict[str, Any]],
    recommendations: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], bool]:
    # Late bind so tests can monkeypatch brainstorm.evaluate_variant_against_rule.
    from libs.validation_lab import brainstorm as core

    rule_by_rec: dict[str, str] = {}
    for rec in recommendations or []:
        if not isinstance(rec, dict):
            continue
        rec_id = str(rec.get("recId") or rec.get("rec_id") or "").strip()
        rule_id = str(rec.get("ruleId") or rec.get("rule_id") or "").strip()
        status = str(rec.get("ruleStatus") or rec.get("rule_status") or "").strip()
        if rec_id and rule_id and status == "active":
            rule_by_rec[rec_id] = rule_id

    stamped: list[dict[str, Any]] = []
    any_evaluated = False
    for raw in variants:
        row = dict(raw)
        target = str(row.get("targetRecId") or "").strip()
        rule_id = rule_by_rec.get(target)
        if not rule_id:
            row["expectedTrigger"] = None
            row["expectedTriggerReason"] = "no recommendation attached"
            stamped.append(row)
            continue
        trigger, reason = core.evaluate_variant_against_rule(rule_id, row)
        any_evaluated = True
        row["expectedTrigger"] = trigger
        row["expectedTriggerReason"] = reason
        stamped.append(row)
    return stamped, any_evaluated


def _merge_propose_results(
    batches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict], set[str], list[dict], str]:
    proposed: list[dict[str, Any]] = []
    concepts: dict[str, dict] = {}
    observables: set[str] = set()
    traces: list[dict[str, Any]] = []
    texts: list[str] = []
    for batch in batches:
        concepts.update(batch.get("seen_concepts") or {})
        observables |= set(batch.get("seen_observables") or set())
        traces.extend(list(batch.get("tool_traces") or []))
        msg = str(batch.get("assistant_message") or "").strip()
        if msg:
            texts.append(msg)
        for row in batch.get("proposed") or []:
            if isinstance(row, dict):
                proposed.append(row)
    return proposed, concepts, observables, traces, " ".join(texts).strip()


def _propose_batches_for_recs(
    *,
    testable: list[dict[str, Any]],
    scenario: str,
    answers: dict[str, Any],
    include_control: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    batches: list[dict[str, Any]] = []
    failed_recs: list[str] = []
    for index, rec in enumerate(testable):
        rec_id = str(rec.get("recId") or rec.get("rec_id") or "").strip()
        last = index == len(testable) - 1
        payload = {
            "phase": "propose_variants",
            "scenario_text": scenario,
            "recommendations": [rec],
            "answers": answers,
            "include_control": bool(include_control) and last,
            "variants_requested": VARIANTS_PER_RECOMMENDATION,
            "instruction": (
                f"Propose exactly {VARIANTS_PER_RECOMMENDATION} "
                "trigger-positive variants for this recommendation. "
                f"Every variant must set targetRecId to {rec_id}."
            ),
        }
        try:
            batch = _propose_once(
                user_payload=payload,
                agent_task="validation_lab_brainstorm_propose",
                variants_requested=VARIANTS_PER_RECOMMENDATION,
            )
        except Exception:
            label = str(rec.get("recTitle") or rec_id or f"#{index + 1}")
            logger.exception("brainstorm.propose failed for %s", label)
            failed_recs.append(label)
            continue
        batch["proposed"] = _stamp_target_rec(
            list(batch.get("proposed") or []),
            rec_id=rec_id,
        )
        batches.append(batch)
    return batches, failed_recs


def _guidance_for_propose(
    *,
    guidance: str,
    failed_recs: list[str],
    variants: list[dict[str, Any]],
    testable: list[dict[str, Any]],
) -> str:
    if failed_recs:
        fail_hint = (
            "Could not generate variants for: "
            + ", ".join(failed_recs)
            + ". Retry those recommendations on their own."
        )
        guidance = f"{guidance} {fail_hint}".strip() if guidance else fail_hint
    if not variants:
        empty_hint = (
            "No variants were generated. The model did not return "
            "propose_variants output. Try Next again, or attach fewer "
            "recommendations and narrow the scenario text."
        )
        return f"{guidance} {empty_hint}".strip() if guidance else empty_hint
    if not testable:
        return guidance
    expected = len(testable) * VARIANTS_PER_RECOMMENDATION
    positives = [v for v in variants if not v.get("isControl")]
    if len(positives) >= expected:
        return guidance
    hint = (
        f"Generated {len(positives)} of {expected} expected variants "
        f"({VARIANTS_PER_RECOMMENDATION} per attached recommendation). "
        "Retry if coverage looks incomplete."
    )
    return f"{guidance} {hint}".strip() if guidance else hint


def run_propose_variants(
    *,
    scenario_text: str = "",
    recommendations: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    include_control: bool = False,
) -> dict[str, Any]:
    """Propose variants: 3 per attached recommendation, or 5 freeform."""
    from libs.validation_lab import brainstorm as core

    testable, skipped, guidance = core._partition_recommendations(recommendations)
    if len(testable) > MAX_BRAINSTORM_RECOMMENDATIONS:
        raise ValueError(_too_many_recs_message(len(testable)))
    scenario = str(scenario_text or "").strip()
    answers = answers or {}
    failed_recs: list[str] = []

    if testable:
        batches, failed_recs = _propose_batches_for_recs(
            testable=testable,
            scenario=scenario,
            answers=answers,
            include_control=include_control,
        )
    else:
        batches = [
            _propose_once(
                user_payload={
                    "phase": "propose_variants",
                    "scenario_text": scenario,
                    "recommendations": [],
                    "answers": answers,
                    "include_control": bool(include_control),
                    "variants_requested": 5,
                    "instruction": (
                        "Propose at most 5 freeform trigger-positive variants."
                    ),
                },
                agent_task="validation_lab_brainstorm_propose",
                variants_requested=5,
            )
        ]

    raw_proposed, seen_concepts, seen_observables, tool_traces, assistant = (
        _merge_propose_results(batches)
    )
    proposed = [
        verify_patch(row, seen_concepts, seen_observables)
        for row in raw_proposed
        if isinstance(row, dict)
    ]
    stamped, rule_evaluated = _stamp_expected_trigger(proposed, testable)
    variants = normalise_variants(stamped, rule_evaluated=rule_evaluated)
    if rule_evaluated:
        by_id = {str(v.get("variantId")): v for v in stamped}
        for row in variants:
            src = by_id.get(str(row.get("variantId")))
            if not src:
                continue
            row["expectedTrigger"] = src.get("expectedTrigger")
            row["expectedTriggerReason"] = src.get("expectedTriggerReason")
    guidance = _guidance_for_propose(
        guidance=guidance,
        failed_recs=failed_recs,
        variants=variants,
        testable=testable,
    )
    return {
        "variants": variants,
        "guidance_message": guidance,
        "recommendations": testable,
        "skipped_recommendations": skipped,
        "assistant_message": assistant,
        "tool_traces": tool_traces,
    }
