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
    SYSTEM_PROMPT,
    UNDERSTAND_TOOL_CONFIG,
)
from libs.validation_lab.brainstorm_tools import search_guidelines, search_snomed
from libs.validation_lab.rule_grounded_eval import (  # noqa: F401
    evaluate_variant_against_rule,  # re-export for propose monkeypatch
)
from libs.validation_lab.scenario_patch import (
    MAX_BRAINSTORM_RECOMMENDATIONS,
    verify_patch,
)

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 4
_MAX_CLARIFY_ROUNDS = 2


def _too_many_recs_message(count: int) -> str:
    return (
        f"Too many recommendations attached ({count}). "
        f"Brainstorm can use at most {MAX_BRAINSTORM_RECOMMENDATIONS} "
        "at a time (about 3 test cases each). Remove some, or use "
        "Select all compiled on a smaller guideline chapter, then try again."
    )


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
    response_items: list[Any] = []
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
            response_items=response_items,
            agent_task=agent_task,
            max_tokens=max_tokens,
        )
        if getattr(resp, "text", None):
            text_parts.append(str(resp.text))
        tool_uses = list(getattr(resp, "tool_uses", None) or [])
        if not tool_uses:
            break
        raw_items = list(getattr(resp, "raw_output_items", None) or [])
        if raw_items:
            response_items.extend(raw_items)
        else:
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
            if raw_items:
                response_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tu_id,
                        "output": json.dumps(payload, ensure_ascii=True),
                    }
                )
        if not raw_items:
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
    if len(testable) > MAX_BRAINSTORM_RECOMMENDATIONS:
        raise ValueError(_too_many_recs_message(len(testable)))
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


def run_propose_variants(
    *,
    scenario_text: str = "",
    recommendations: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    include_control: bool = False,
) -> dict[str, Any]:
    """Propose variants: 3 per attached recommendation, or 5 freeform."""
    from libs.validation_lab.brainstorm_propose import (
        run_propose_variants as _run,
    )

    return _run(
        scenario_text=scenario_text,
        recommendations=recommendations,
        answers=answers,
        include_control=include_control,
    )
