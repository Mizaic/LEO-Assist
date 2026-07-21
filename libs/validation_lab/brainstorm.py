"""Validation Lab guided scenario-variant brainstorm service.

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

from libs.guidance.recommendation_triage import (
    default_selected_for_triage,
    triage_recommendation,
)
from libs.prompts.validation_lab_brainstorm_v1 import (
    PROPOSE_TOOL_CONFIG,
    PROPOSE_VARIANTS_TOOL,
    SYSTEM_PROMPT,
    UNDERSTAND_TOOL_CONFIG,
)
from libs.validation_lab.brainstorm_tools import search_guidelines, search_snomed
from libs.validation_lab.rule_grounded_eval import evaluate_variant_against_rule
from libs.validation_lab.scenario_patch import (
    VARIANTS_PER_RECOMMENDATION,
    normalise_variants,
    verify_patch,
)

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 4
_MAX_CLARIFY_ROUNDS = 2


def _build_tool_result_block(tool_use_id: str, payload: dict[str, Any]) -> dict:
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"json": payload}],
        }
    }


def _partition_recommendations(
    recommendations: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    testable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in recommendations or []:
        if not isinstance(raw, dict):
            continue
        verbatim = str(raw.get("verbatim") or "")
        bucket = triage_recommendation(verbatim)
        row = dict(raw)
        row["triage"] = bucket
        if default_selected_for_triage(bucket):
            testable.append(row)
        else:
            skipped.append(row)
    if not (recommendations or []):
        return [], [], ""
    if not testable:
        return (
            [],
            skipped,
            (
                "This describes a process requirement or information-only "
                "recommendation, not a patient-level clinical trigger, so "
                "there is nothing to build a test scenario from. Try "
                "selecting a different recommendation."
            ),
        )
    if skipped:
        titles = ", ".join(
            str(s.get("recTitle") or s.get("rec_id") or s.get("recId") or "?")
            for s in skipped
        )
        msg = f"Skipped non-testable recommendations: {titles}."
        return testable, skipped, msg
    return testable, skipped, ""


def _dispatch_tool(
    name: str,
    inp: dict[str, Any],
    *,
    seen_concepts: dict[str, dict],
    seen_observables: set[str],
    proposed: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    if name == "search_snomed":
        tags = inp.get("semantic_tags")
        candidates = search_snomed(
            str(inp.get("query") or ""),
            semantic_tags=list(tags) if isinstance(tags, list) else None,
        )
        for c in candidates:
            seen_concepts[c["concept_id"]] = c
            if "observable" in str(c.get("semantic_tag") or "").lower():
                seen_observables.add(c["concept_id"])
            if tags and "observable_entity" in tags:
                seen_observables.add(c["concept_id"])
        return {"ok": True, "candidates": candidates}
    if name == "search_guidelines":
        return {
            "ok": True,
            "guidelines": search_guidelines(str(inp.get("query") or "")),
        }
    if name == "gather_scenario_questions":
        questions.clear()
        questions.extend(list(inp.get("questions") or []))
        return {"ok": True, "question_count": len(questions)}
    if name == "propose_variants":
        proposed.clear()
        rows = _variant_rows_from_tool_input(inp)
        for row in rows:
            if isinstance(row, dict):
                proposed.append(verify_patch(row, seen_concepts, seen_observables))
        return {"ok": True, "accepted_count": len(proposed)}
    return {"ok": False, "error": f"unsupported_tool:{name}"}


def _variant_rows_from_tool_input(inp: dict[str, Any]) -> list[Any]:
    """Accept common LLM key variants for the propose_variants payload."""
    for key in ("variants", "Variants", "scenario_variants", "scenarioVariants"):
        rows = inp.get(key)
        if isinstance(rows, list) and rows:
            return rows
    return []


def _forced_propose_tool_config() -> dict[str, Any]:
    """Bedrock toolChoice that requires propose_variants (no prose-only exit)."""
    return {
        "tools": [PROPOSE_VARIANTS_TOOL],
        "toolChoice": {"tool": {"name": "propose_variants"}},
    }


def _run_tool_loop(
    *,
    messages: list[dict[str, Any]],
    tool_config: dict[str, Any],
    agent_task: str,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    from libs.llm_client.factory import create_llm

    llm = create_llm(tier="small")
    convo = list(messages)
    seen_concepts: dict[str, dict] = {}
    seen_observables: set[str] = set()
    proposed: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    text_parts: list[str] = []
    tool_traces: list[dict[str, Any]] = []

    for _ in range(_MAX_TOOL_ITERATIONS):
        resp = llm.converse(
            system=SYSTEM_PROMPT,
            messages=convo,
            tool_config=tool_config,
            agent_task=agent_task,
            max_tokens=max_tokens,
        )
        if getattr(resp, "text", None):
            text_parts.append(str(resp.text))
        tool_uses = list(getattr(resp, "tool_uses", None) or [])
        if not tool_uses:
            break
        assistant_content: list[dict[str, Any]] = []
        if resp.text:
            assistant_content.append({"text": resp.text})
        assistant_content.extend({"toolUse": tu} for tu in tool_uses)
        convo.append({"role": "assistant", "content": assistant_content})
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            name = str(tu.get("name") or "")
            tu_id = str(tu.get("toolUseId") or "")
            inp = dict(tu.get("input") or {})
            payload = _dispatch_tool(
                name,
                inp,
                seen_concepts=seen_concepts,
                seen_observables=seen_observables,
                proposed=proposed,
                questions=questions,
            )
            tool_traces.append(
                {
                    "tool": name,
                    "input": inp,
                    "ok": bool(payload.get("ok")),
                }
            )
            tool_results.append(_build_tool_result_block(tu_id, payload))
        convo.append({"role": "user", "content": tool_results})

    return {
        "assistant_message": " ".join(text_parts).strip(),
        "questions": questions,
        "proposed": proposed,
        "tool_traces": tool_traces,
        "seen_concepts": seen_concepts,
        "seen_observables": seen_observables,
    }


def run_understand_or_clarify(
    *,
    phase: str,
    scenario_text: str = "",
    recommendations: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    round: int = 0,
) -> dict[str, Any]:
    """Run understand or clarify phase with triage short-circuit and round cap."""
    text = str(scenario_text or "").strip()
    testable, skipped, guidance = _partition_recommendations(recommendations)
    if (recommendations or []) and not testable:
        return {
            "needs_clarification": False,
            "questions": [],
            "guidance_message": guidance,
            "recommendations": [],
            "skipped_recommendations": skipped,
            "assistant_message": guidance,
            "tool_traces": [],
        }
    if not text and not testable:
        raise ValueError("scenario_text or recommendations required")

    if phase == "clarify" and int(round) >= _MAX_CLARIFY_ROUNDS:
        return {
            "needs_clarification": False,
            "questions": [],
            "guidance_message": guidance,
            "recommendations": testable,
            "skipped_recommendations": skipped,
            "assistant_message": "Enough detail gathered to propose variants.",
            "tool_traces": [],
        }

    user_payload = {
        "phase": phase,
        "scenario_text": text,
        "recommendations": testable,
        "answers": answers or {},
        "round": int(round),
    }
    result = _run_tool_loop(
        messages=[{"role": "user", "content": json.dumps(user_payload)}],
        tool_config=UNDERSTAND_TOOL_CONFIG,
        agent_task="validation_lab_brainstorm_understand",
    )
    questions = list(result.get("questions") or [])
    needs = bool(questions) and not (
        phase == "clarify" and int(round) >= _MAX_CLARIFY_ROUNDS
    )
    return {
        "needs_clarification": needs,
        "questions": questions if needs else [],
        "guidance_message": guidance,
        "recommendations": testable,
        "skipped_recommendations": skipped,
        "assistant_message": result.get("assistant_message") or "",
        "tool_traces": result.get("tool_traces") or [],
    }


def _stamp_expected_trigger(
    variants: list[dict[str, Any]],
    recommendations: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], bool]:
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
        trigger, reason = evaluate_variant_against_rule(rule_id, row)
        any_evaluated = True
        row["expectedTrigger"] = trigger
        row["expectedTriggerReason"] = reason
        stamped.append(row)
    return stamped, any_evaluated


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


def _propose_once(
    *,
    user_payload: dict[str, Any],
    agent_task: str,
    variants_requested: int,
) -> dict[str, Any]:
    """Run propose tool loop once, with forced retry if empty."""
    messages = [{"role": "user", "content": json.dumps(user_payload)}]
    result = _run_tool_loop(
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
    return _run_tool_loop(
        messages=[*messages, {"role": "user", "content": nudge}],
        tool_config=_forced_propose_tool_config(),
        agent_task=f"{agent_task}_retry",
        max_tokens=4096,
    )


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


def run_propose_variants(
    *,
    scenario_text: str = "",
    recommendations: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    include_control: bool = False,
) -> dict[str, Any]:
    """Propose variants: 3 per attached recommendation, or 5 freeform."""
    testable, skipped, guidance = _partition_recommendations(recommendations)
    scenario = str(scenario_text or "").strip()
    batches: list[dict[str, Any]] = []

    if testable:
        for index, rec in enumerate(testable):
            rec_id = str(rec.get("recId") or rec.get("rec_id") or "").strip()
            last = index == len(testable) - 1
            payload = {
                "phase": "propose_variants",
                "scenario_text": scenario,
                "recommendations": [rec],
                "answers": answers or {},
                "include_control": bool(include_control) and last,
                "variants_requested": VARIANTS_PER_RECOMMENDATION,
                "instruction": (
                    f"Propose exactly {VARIANTS_PER_RECOMMENDATION} "
                    "trigger-positive variants for this recommendation. "
                    f"Every variant must set targetRecId to {rec_id}."
                ),
            }
            batch = _propose_once(
                user_payload=payload,
                agent_task="validation_lab_brainstorm_propose",
                variants_requested=VARIANTS_PER_RECOMMENDATION,
            )
            batch["proposed"] = _stamp_target_rec(
                list(batch.get("proposed") or []),
                rec_id=rec_id,
            )
            batches.append(batch)
    else:
        payload = {
            "phase": "propose_variants",
            "scenario_text": scenario,
            "recommendations": [],
            "answers": answers or {},
            "include_control": bool(include_control),
            "variants_requested": 5,
            "instruction": "Propose at most 5 freeform trigger-positive variants.",
        }
        batches.append(
            _propose_once(
                user_payload=payload,
                agent_task="validation_lab_brainstorm_propose",
                variants_requested=5,
            )
        )

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
    if not variants:
        empty_hint = (
            "No variants were generated. The model did not return "
            "propose_variants output. Try Next again, or attach fewer "
            "recommendations and narrow the scenario text."
        )
        guidance = f"{guidance} {empty_hint}".strip() if guidance else empty_hint
    elif testable:
        expected = len(testable) * VARIANTS_PER_RECOMMENDATION
        positives = [v for v in variants if not v.get("isControl")]
        if len(positives) < expected:
            hint = (
                f"Generated {len(positives)} of {expected} expected variants "
                f"({VARIANTS_PER_RECOMMENDATION} per attached recommendation). "
                "Retry if coverage looks incomplete."
            )
            guidance = f"{guidance} {hint}".strip() if guidance else hint
    return {
        "variants": variants,
        "guidance_message": guidance,
        "recommendations": testable,
        "skipped_recommendations": skipped,
        "assistant_message": assistant,
        "tool_traces": tool_traces,
    }
