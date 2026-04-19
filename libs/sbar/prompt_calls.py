"""LLM call wrappers for the three SBAR prompts.

Centralised so the orchestrator stays focused on flow control and so the
prompt-rendering rules (CONTEXT serialisation, sanitisation, fallback
handling) live in one place.

Each function returns a dict with:
  - ``markdown``  - the section text
  - ``raw``       - the raw LLM JSON (for storage/audit)
  - ``error``     - a string if the call failed, otherwise None
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from libs.llm_client.json_helper import invoke_llm_json
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.prompts.registry import get_prompt
from libs.sbar.background_partitioner import (
    Partition,
    PartitionReport,
    partition_background_sources,
)
from libs.sbar.error_messages import translate_error
from libs.sbar.source_resolver import (
    ResolvedCode,
    ResolvedSituation,
    ResolvedSource,
)

logger = logging.getLogger(__name__)


_PROMPT_NAME_SITUATION = "sbar_situation"
_PROMPT_NAME_BACKGROUND = "sbar_background"
_PROMPT_NAME_BACKGROUND_REDUCE = "sbar_background_reduce"
_PROMPT_NAME_RECOMMENDATION = "sbar_recommendation"


# Type for the per-part progress callback supplied by the
# orchestrator. The orchestrator wires this into an
# ``sbar_stage_progress`` SSE event so the UI can render
# "Generating Background (part 2 of 5)..." instead of looking hung.
PartProgressCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Context serialisation
# ---------------------------------------------------------------------------


def _serialise_situation_context(
    resolved: ResolvedSituation,
    *,
    extra_context: dict[str, Any] | None = None,
) -> str:
    body = {
        "patient": {
            "id": resolved.patient_id,
            "gender": resolved.patient_summary.get("gender"),
            "birth_date": resolved.patient_summary.get("birth_date"),
        },
        "artifacts": [
            {
                k: sanitise_for_prompt(v) if isinstance(v, str) else v
                for k, v in artefact.items()
            }
            for artefact in resolved.artifacts
        ],
        "extra": extra_context or {},
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _serialise_background_reduce_context(
    *,
    parts: list[dict[str, Any]],
) -> str:
    """User message for the REDUCE step.

    ``parts`` is the per-part LLM JSON output collected by
    ``call_background``. Each entry already conforms to
    ``SBAR_BACKGROUND_OUTPUT_SCHEMA`` so we can pass it through
    near-verbatim; we only re-stamp ``part_index`` / ``part_total``
    so the merge prompt's HARD RULES line up with the input.
    """
    body = {"parts": parts}
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _serialise_recommendation_context(
    *,
    situation_md: str,
    background_md: str,
    assessment_md: str,
    assessment_rules: list[dict[str, Any]],
    guideline_titles: list[str],
    guidelines: list[str],
) -> str:
    body = {
        "situation": situation_md,
        "background": background_md,
        "assessment": assessment_md,
        "assessment_rules": assessment_rules,
        "guideline_titles": guideline_titles,
        "guidelines": guidelines,
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


PromptFetcher = Callable[[str], str]


# SBAR prompts are pinned to v2 -- plain-English narrative with inline
# [date] markers only (no encounter / document ids). v1 stays seeded for
# audit / rollback. See DO-LEO-AI-191.
_SBAR_PROMPT_VERSIONS: dict[str, int] = {
    _PROMPT_NAME_SITUATION: 2,
    _PROMPT_NAME_BACKGROUND: 2,
    _PROMPT_NAME_BACKGROUND_REDUCE: 1,
    _PROMPT_NAME_RECOMMENDATION: 2,
}


def _default_prompt(name: str) -> str:
    return get_prompt(name, version=_SBAR_PROMPT_VERSIONS.get(name, 1))


async def call_situation(
    resolved: ResolvedSituation,
    *,
    extra_context: dict[str, Any] | None = None,
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
) -> dict[str, Any]:
    system = prompt_fetcher(_PROMPT_NAME_SITUATION)
    user = _serialise_situation_context(resolved, extra_context=extra_context)
    raw = await invoker(
        system,
        user,
        max_tokens=512,
        temperature=0.0,
        agent_task="sbar_situation",
        patient_id=patient_id,
    )
    if "error" in raw:
        friendly = translate_error("situation", raw["error"])
        return {
            "markdown": "",
            "raw": raw,
            "error": friendly["message"],
            "error_code": friendly["code"],
        }
    md = (raw.get("situation_markdown") or "").strip()
    if md:
        return {"markdown": md, "raw": raw, "error": None, "error_code": None}
    friendly = translate_error("situation", "missing_situation_markdown")
    return {
        "markdown": md,
        "raw": raw,
        "error": friendly["message"],
        "error_code": friendly["code"],
    }


def _stitch_partials_deterministic(
    parts: list[dict[str, Any]],
) -> str:
    """Fallback stitch when REDUCE is not run or fails.

    Concatenates each part's ``background_markdown`` under a clear
    ``### Part i of N`` heading so the reviewer can see exactly
    which part each bullet came from. Failed parts are rendered as
    a placeholder so the reader can see the gap rather than
    silently missing records.
    """
    chunks: list[str] = []
    for part in parts:
        idx = part.get("part_index")
        total = part.get("part_total")
        record_count = part.get("record_count") or 0
        heading = f"### Part {idx} of {total} -- {record_count} records"
        if part.get("error_message"):
            chunks.append(
                f"{heading}\n\n_This part did not finish: "
                f"{part['error_message']}_"
            )
            continue
        md = (part.get("background_markdown") or "").strip()
        chunks.append(f"{heading}\n\n{md}" if md else heading)
    return "\n\n".join(chunks)


async def _invoke_background_part(
    partition: Partition,
    *,
    system: str,
    invoker: Callable[..., Awaitable[dict[str, Any]]],
    patient_id: str,
) -> dict[str, Any]:
    """Run one map step. Returns a per-part dict suitable for stitch + reduce."""
    raw = await invoker(
        system,
        partition.user_message,
        max_tokens=1024,
        temperature=0.0,
        agent_task="sbar_background",
        patient_id=patient_id,
    )
    base: dict[str, Any] = {
        "part_index": partition.index,
        "part_total": partition.total,
        "record_count": len(
            {d.source_id for d in partition.descriptors}
        ),
        "descriptors": [d.__dict__ for d in partition.descriptors],
        "raw": raw,
    }
    if "error" in raw:
        friendly = translate_error("background", raw["error"])
        return {
            **base,
            "background_markdown": "",
            "citations": [],
            "missing": [],
            "conflicts": [],
            "error_code": friendly["code"],
            "error_message": friendly["message"],
        }
    md = (raw.get("background_markdown") or "").strip()
    if not md:
        friendly = translate_error("background", "missing_background_markdown")
        return {
            **base,
            "background_markdown": "",
            "citations": list(raw.get("citations") or []),
            "missing": list(raw.get("missing") or []),
            "conflicts": list(raw.get("conflicts") or []),
            "error_code": friendly["code"],
            "error_message": friendly["message"],
        }
    return {
        **base,
        "background_markdown": md,
        "citations": list(raw.get("citations") or []),
        "missing": list(raw.get("missing") or []),
        "conflicts": list(raw.get("conflicts") or []),
        "error_code": None,
        "error_message": None,
    }


async def _try_reduce_partials(
    parts: list[dict[str, Any]],
    *,
    system: str,
    invoker: Callable[..., Awaitable[dict[str, Any]]],
    patient_id: str,
) -> dict[str, Any]:
    """Run the REDUCE step. Returns dict with merged_markdown or error."""
    user = _serialise_background_reduce_context(
        parts=[
            {
                "part_index": p["part_index"],
                "part_total": p["part_total"],
                "background_markdown": p["background_markdown"],
                "citations": p["citations"],
                "missing": p["missing"],
                "conflicts": p["conflicts"],
            }
            for p in parts
        ],
    )
    raw = await invoker(
        system,
        user,
        max_tokens=2048,
        temperature=0.0,
        agent_task="sbar_background_reduce",
        patient_id=patient_id,
    )
    if "error" in raw:
        friendly = translate_error("background", "reduce_failed")
        return {
            "markdown": "",
            "raw": raw,
            "error_code": friendly["code"],
            "error_message": friendly["message"],
        }
    md = (raw.get("background_markdown") or "").strip()
    if not md:
        friendly = translate_error("background", "reduce_failed")
        return {
            "markdown": "",
            "raw": raw,
            "error_code": friendly["code"],
            "error_message": friendly["message"],
        }
    return {"markdown": md, "raw": raw, "error_code": None, "error_message": None}


def _build_part_summary(
    part: dict[str, Any],
) -> dict[str, Any]:
    """Slim wire payload for the SSE / orchestrator audit trail."""
    return {
        "index": part["part_index"],
        "total": part["part_total"],
        "record_count": part["record_count"],
        "status": "completed" if not part.get("error_code") else "failed",
        "error_code": part.get("error_code"),
        "error_message": part.get("error_message"),
    }


async def call_background(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None = None,
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
    progress_cb: PartProgressCallback | None = None,
) -> dict[str, Any]:
    """Generate the SBAR Background section, splitting the run if needed.

    Strategy: partition + map + reduce.

    1. PARTITION the sources into N <= 8 LLM-sized parts. Every
       record is preserved; nothing is dropped.
    2. MAP -- run the standard sbar_background prompt once per
       partition (sequentially). Per-part failures are contained.
    3. REDUCE -- if N >= 2 AND every part succeeded, run the
       sbar_background_reduce prompt to merge the partials into a
       single coherent Background. If the REDUCE call fails, fall
       back to deterministic stitching with clear "Part i of N"
       subheadings.

    The ``progress_cb`` lets the orchestrator emit per-part
    ``sbar_stage_progress`` SSE events so the UI shows
    "Generating Background (part 2 of 5)..." instead of looking
    hung for 30s.
    """
    system_map = prompt_fetcher(_PROMPT_NAME_BACKGROUND)
    partitions, partition_report = partition_background_sources(
        sources, codes, referring_specialty=referring_specialty
    )

    notices: list[str] = []
    if partition_report.notice:
        notices.append(partition_report.notice)
    if partition_report.record_split_notice:
        notices.append(partition_report.record_split_notice)

    base_response: dict[str, Any] = {
        "raw": {},
        "notice": " ".join(notices) if notices else None,
        "shrink_report": None,
        "partition_report": partition_report,
        "parts": [],
    }

    if partition_report.too_many_parts:
        friendly = translate_error("background", "too_many_parts")
        logger.warning(
            "SBAR background partitioner refused: too_many_parts records=%d",
            partition_report.total_records,
        )
        return {
            **base_response,
            "markdown": "",
            "error": friendly["message"],
            "error_code": friendly["code"],
        }

    # MAP -- one LLM call per partition, sequential.
    part_results: list[dict[str, Any]] = []
    for partition in partitions:
        if progress_cb is not None:
            progress_cb(
                {
                    "phase": "map",
                    "part_index": partition.index,
                    "part_total": partition.total,
                    "record_count": len(
                        {d.source_id for d in partition.descriptors}
                    ),
                    "status": "started",
                }
            )
        result = await _invoke_background_part(
            partition,
            system=system_map,
            invoker=invoker,
            patient_id=patient_id,
        )
        part_results.append(result)
        if progress_cb is not None:
            progress_cb(
                {
                    "phase": "map",
                    "part_index": partition.index,
                    "part_total": partition.total,
                    "record_count": result["record_count"],
                    "status": "failed" if result["error_code"] else "completed",
                    "error_code": result["error_code"],
                }
            )

    parts_summary = [_build_part_summary(p) for p in part_results]
    failed_parts = [p for p in part_results if p["error_code"]]
    succeeded_parts = [p for p in part_results if not p["error_code"]]

    # Single-partition path: behave like the legacy single-call
    # Background -- no reduce, no notice, just return the one part.
    if len(part_results) == 1:
        only = part_results[0]
        return {
            **base_response,
            "markdown": only["background_markdown"],
            "error": only["error_message"],
            "error_code": only["error_code"],
            "raw": only["raw"],
            "parts": parts_summary,
        }

    # Multi-partition path. Attempt REDUCE only when every part
    # succeeded -- merging a partial set of parts would silently
    # imply the missing parts were empty, which violates the
    # no-record-dropped invariant.
    reduced: dict[str, Any] | None = None
    if not failed_parts and succeeded_parts:
        if progress_cb is not None:
            progress_cb({"phase": "reduce", "status": "started"})
        system_reduce = prompt_fetcher(_PROMPT_NAME_BACKGROUND_REDUCE)
        reduced = await _try_reduce_partials(
            succeeded_parts,
            system=system_reduce,
            invoker=invoker,
            patient_id=patient_id,
        )
        if progress_cb is not None:
            progress_cb(
                {
                    "phase": "reduce",
                    "status": (
                        "failed" if reduced["error_code"] else "completed"
                    ),
                    "error_code": reduced.get("error_code"),
                }
            )

    if reduced and not reduced["error_code"]:
        return {
            **base_response,
            "markdown": reduced["markdown"],
            "raw": reduced["raw"],
            "error": None,
            "error_code": None,
            "parts": parts_summary,
        }

    # Fallback: deterministic stitch. Either the REDUCE failed, or
    # at least one MAP part failed (so we don't try to REDUCE).
    stitched = _stitch_partials_deterministic(part_results)
    error_message: str | None = None
    error_code: str | None = None
    if failed_parts:
        # background_part_failed wins over reduce_failed because
        # the reviewer's primary action ("re-run / pick fewer
        # records") is the same and the part failure is the more
        # actionable signal.
        friendly = translate_error("background", "background_part_failed")
        error_message = friendly["message"]
        error_code = friendly["code"]
    elif reduced and reduced["error_code"]:
        error_message = reduced["error_message"]
        error_code = reduced["error_code"]
        # Surface the reduce failure to the reviewer as a notice as
        # well, so they understand the "side by side" layout.
        notices.append(
            "We summarised the records in parts but could not merge "
            "them into one section, so they are shown side by side."
        )
        base_response["notice"] = " ".join(notices)

    return {
        **base_response,
        "markdown": stitched,
        "raw": (reduced or {}).get("raw") or {},
        "error": error_message,
        "error_code": error_code,
        "parts": parts_summary,
    }


async def call_recommendation(
    *,
    situation_md: str,
    background_md: str,
    assessment_md: str,
    assessment_rules: list[dict[str, Any]],
    guideline_titles: list[str],
    guidelines: list[str],
    patient_id: str = "",
    prompt_fetcher: PromptFetcher = _default_prompt,
    invoker: Callable[..., Awaitable[dict[str, Any]]] = invoke_llm_json,
) -> dict[str, Any]:
    system = prompt_fetcher(_PROMPT_NAME_RECOMMENDATION)
    user = _serialise_recommendation_context(
        situation_md=situation_md,
        background_md=background_md,
        assessment_md=assessment_md,
        assessment_rules=assessment_rules,
        guideline_titles=guideline_titles,
        guidelines=guidelines,
    )
    raw = await invoker(
        system,
        user,
        max_tokens=1024,
        temperature=0.0,
        agent_task="sbar_recommendation",
        patient_id=patient_id,
    )
    if "error" in raw:
        friendly = translate_error("recommendation", raw["error"])
        return {
            "markdown": "",
            "actions": [],
            "raw": raw,
            "error": friendly["message"],
            "error_code": friendly["code"],
        }
    md = (raw.get("recommendation_markdown") or "").strip()
    actions = list(raw.get("actions") or [])
    if md:
        return {
            "markdown": md,
            "actions": actions,
            "raw": raw,
            "error": None,
            "error_code": None,
        }
    friendly = translate_error("recommendation", "missing_recommendation_markdown")
    return {
        "markdown": md,
        "actions": actions,
        "raw": raw,
        "error": friendly["message"],
        "error_code": friendly["code"],
    }
