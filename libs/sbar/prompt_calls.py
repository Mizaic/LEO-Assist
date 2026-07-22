"""LLM call wrappers for the three SBAR prompts.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

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
import re
from typing import Any, Awaitable, Callable

from libs.llm_client.json_helper import invoke_llm_json
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.prompts.registry import get_prompt
from libs.sbar.assessment_formatter import STRENGTH_RANK
from libs.sbar.background_partitioner import (
    Partition,
    partition_background_sources,
)
from libs.sbar.error_messages import translate_error
from libs.sbar.source_resolver import (
    ResolvedCode,
    ResolvedSituation,
    ResolvedSource,
)
from libs.sbar.uncoded_coverage import CoverageReport

logger = logging.getLogger(__name__)


_PROMPT_NAME_SITUATION = "sbar_situation"
_PROMPT_NAME_BACKGROUND = "sbar_background"
_PROMPT_NAME_RECOMMENDATION = "sbar_recommendation"
_PROMPT_NAME_RECALL = "sbar_recall"


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


def _select_primary_rule_id(rules: list[dict[str, Any]]) -> str | None:
    """Deterministically pick the rule that anchors bullet-1.

    Sort order (lower = preferred):
      1. action.priority: 2ww (0) > urgent (1) > routine (2) > other (9)
      2. strength: refer (0) > offer (1) > consider (2) > other (9)

    This is evaluated in Python so the LLM never makes this judgement.
    """
    priority_rank = {"2ww": 0, "urgent": 1, "routine": 2}

    def _sort_key(r: dict[str, Any]) -> tuple[int, int]:
        action = r.get("action") or {}
        p = priority_rank.get((action.get("priority") or "").lower(), 9)
        s = STRENGTH_RANK.get((r.get("strength") or "").lower(), 9)
        return (p, s)

    if not rules:
        return None
    best = min(rules, key=_sort_key)
    return best.get("rule_id")


def _serialise_recommendation_context(
    *,
    situation_md: str,
    background_md: str,
    assessment_md: str,
    assessment_rules: list[dict[str, Any]],
    guideline_titles: list[str],
    guidelines: list[str],
) -> str:
    primary_rule_id = _select_primary_rule_id(assessment_rules)
    body = {
        "situation": situation_md,
        "background": background_md,
        "assessment": assessment_md,
        "assessment_rules": assessment_rules,
        "primary_rule_id": primary_rule_id,
        "guideline_titles": guideline_titles,
        "guidelines": guidelines,
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


PromptFetcher = Callable[[str], str]


# Legacy fallback for tests and non-durable callers without an execution manifest.
_LEGACY_SBAR_PROMPT_VERSIONS: dict[str, int] = {
    _PROMPT_NAME_SITUATION: 2,
    _PROMPT_NAME_BACKGROUND: 2,
    _PROMPT_NAME_RECOMMENDATION: 2,
    _PROMPT_NAME_RECALL: 1,
}


def _default_prompt(name: str) -> str:
    return get_prompt(name, version=_LEGACY_SBAR_PROMPT_VERSIONS.get(name, 1))


def _resolve_prompt_fetcher(
    prompt_fetcher: PromptFetcher | None,
) -> PromptFetcher:
    return prompt_fetcher or _default_prompt


def _resolve_invoker(
    invoker: Callable[..., Awaitable[dict[str, Any]]] | None,
    *,
    stage: str,
    policy_runtime: Any | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    if invoker is not None:
        return invoker
    if policy_runtime is not None:
        from libs.sbar.policy_runtime import make_llm_invoker

        return make_llm_invoker(policy_runtime, stage)
    return invoke_llm_json


async def call_situation(
    resolved: ResolvedSituation,
    *,
    extra_context: dict[str, Any] | None = None,
    patient_id: str = "",
    prompt_fetcher: PromptFetcher | None = None,
    invoker: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    policy_runtime: Any | None = None,
) -> dict[str, Any]:
    fetcher = _resolve_prompt_fetcher(prompt_fetcher)
    if policy_runtime is not None and prompt_fetcher is None:
        from libs.sbar.policy_runtime import make_prompt_fetcher

        fetcher = make_prompt_fetcher(policy_runtime)
    llm = _resolve_invoker(invoker, stage="situation", policy_runtime=policy_runtime)
    llm_params = {}
    if policy_runtime is not None:
        from libs.sbar.policy_runtime import stage_llm_params

        llm_params = stage_llm_params(policy_runtime, "situation")
    system = fetcher(_PROMPT_NAME_SITUATION)
    user = _serialise_situation_context(resolved, extra_context=extra_context)
    raw = await llm(
        system,
        user,
        max_tokens=llm_params.get("max_tokens", 512),
        temperature=llm_params.get("temperature", 0.0),
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


def _format_record_range(start: int, end: int) -> str:
    """Render the ``records {a}-{b}`` clause in a part heading.

    ``start == end`` collapses to ``record {a}`` so a single-record
    part doesn't read awkwardly as "records 7-7".
    """
    if start <= 0 or end <= 0:
        return "no records"
    if start == end:
        return f"record {start}"
    return f"records {start}-{end}"


def _stitch_partials_deterministic(parts: list[dict[str, Any]]) -> str:
    """Stitch per-part Background outputs into one markdown block.

    Each part renders as::

        ### Part {i} of {N} -- records {a}-{b}

        {part markdown}

    The per-part ``source_ids`` are intentionally NOT embedded here.
    They live on the structured ``parts`` field returned by
    ``call_background`` (and persisted as ``background_parts`` on the
    :Assessment node) so the UI can render them as a separate
    "Show source records" disclosure rather than leaking raw UUIDs
    into the rendered Background. Embedding HTML comments here was
    fragile: any markdown renderer that does not strip comments
    (e.g. Tiptap with ``html: false``) treats them as visible text.

    Failed parts get the heading ``### Part {i} of {N} -- records
    {a}-{b} -- this part did not finish`` and a placeholder body
    pointing the reader at the errors panel, so missing parts are
    visible in the rendered Background rather than silently
    swallowed.
    """
    chunks: list[str] = []
    for part in parts:
        idx = part.get("part_index")
        total = part.get("part_total")
        rr = part.get("record_range") or (0, 0)
        rr_text = _format_record_range(int(rr[0]), int(rr[1]))
        if part.get("error_message"):
            heading = (
                f"### Part {idx} of {total} -- {rr_text} " "-- this part did not finish"
            )
            body = (
                "(Background for these records could not be generated. "
                "See the errors panel above.)"
            )
            chunks.append("\n\n".join([heading, body]))
            continue
        heading = f"### Part {idx} of {total} -- {rr_text}"
        md = (part.get("background_markdown") or "").strip()
        body_pieces = [heading]
        if md:
            body_pieces.append(md)
        chunks.append("\n\n".join(body_pieces))
    return "\n\n".join(chunks)


async def _invoke_background_part(
    partition: Partition,
    *,
    system: str,
    invoker: Callable[..., Awaitable[dict[str, Any]]],
    patient_id: str,
    llm_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one map step. Returns a per-part dict ready for the
    deterministic stitch."""
    params = llm_params or {"max_tokens": 1024, "temperature": 0.0}
    raw = await invoker(
        system,
        partition.user_message,
        max_tokens=int(params.get("max_tokens") or 1024),
        temperature=float(params.get("temperature") or 0.0),
        agent_task="sbar_background",
        patient_id=patient_id,
    )
    # source_ids preserved in input order (descriptors already are);
    # de-duplicated so a record split across slices in the same part
    # only appears once in the heading's HTML comment.
    seen_ids: list[str] = []
    for d in partition.descriptors:
        if d.source_id not in seen_ids:
            seen_ids.append(d.source_id)
    base: dict[str, Any] = {
        "part_index": partition.index,
        "part_total": partition.total,
        "record_count": len(seen_ids),
        "record_range": partition.record_range,
        "source_ids": seen_ids,
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


_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:",
    re.IGNORECASE,
)


def _friendly_source_label(source_id: str, source_type: str = "") -> str:
    """Clinician-facing chip label from a raw source id + type."""
    text = str(source_id or "").strip()
    if not text:
        return source_type or "Clinical record"
    stripped = _UUID_PREFIX_RE.sub("", text)
    parts = stripped.split(":")
    if len(parts) >= 2 and stripped != text:
        label = ":".join(parts[:-1])
        kind = parts[-1]
        return f"{label} ({kind})"
    if source_type:
        short = (
            stripped if len(stripped) <= 24 else f"{stripped[:10]}...{stripped[-6:]}"
        )
        return f"{source_type}: {short}"
    if len(stripped) > 28:
        return f"Clinical record ({stripped[:8]}...)"
    return stripped


def _sources_from_part(part: dict[str, Any]) -> list[dict[str, Any]]:
    """Build enriched source refs for the widget disclosure."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for d in part.get("descriptors") or []:
        if isinstance(d, dict):
            sid = str(d.get("source_id") or "").strip()
            stype = str(d.get("source_label") or "")
            preview = str(d.get("preview") or "")
        else:
            sid = str(getattr(d, "source_id", "") or "").strip()
            stype = str(getattr(d, "source_label", "") or "")
            preview = str(getattr(d, "preview", "") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(
            {
                "id": sid,
                "type": stype or "Record",
                "label": _friendly_source_label(sid, stype),
                "preview": preview[:200],
            }
        )
    if out:
        return out
    for sid in part.get("source_ids") or []:
        text = str(sid or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(
            {
                "id": text,
                "type": "Record",
                "label": _friendly_source_label(text),
                "preview": "",
            }
        )
    return out


def _build_part_summary(
    part: dict[str, Any],
) -> dict[str, Any]:
    """Slim wire payload for the SSE / orchestrator audit trail."""
    rr = part.get("record_range") or (0, 0)
    return {
        "index": part["part_index"],
        "total": part["part_total"],
        "record_count": part["record_count"],
        "record_range": [int(rr[0]), int(rr[1])],
        "source_ids": list(part.get("source_ids") or []),
        "sources": _sources_from_part(part),
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
    coverage: CoverageReport | None = None,
    prompt_fetcher: PromptFetcher | None = None,
    invoker: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    progress_cb: PartProgressCallback | None = None,
    policy_runtime: Any | None = None,
) -> dict[str, Any]:
    """Generate the SBAR Background section, splitting the run if needed.

    Strategy: partition + map + deterministic stitch (no reduce).

    1. PARTITION the sources into N <= 8 LLM-sized parts. Every
       record is preserved; nothing is dropped.
    2. MAP -- run the standard sbar_background prompt once per
       partition (sequentially). Per-part failures are contained:
       a failed part renders as a "this part did not finish"
       placeholder while the surviving parts still land.
    3. STITCH -- pure-Python concatenation under
       ``### Part {i} of {N} -- records {a}-{b}`` headings. There
       is intentionally no LLM merge step: a reduce call is itself
       a place the LLM could drop or distort detail, which is the
       thing this whole feature was built to avoid.

    The ``progress_cb`` lets the orchestrator emit per-part
    ``sbar_stage_progress`` SSE events so the UI shows
    "Generating Background (part 2 of 5)..." instead of looking
    hung for 30s.
    """
    fetcher = _resolve_prompt_fetcher(prompt_fetcher)
    if policy_runtime is not None and prompt_fetcher is None:
        from libs.sbar.policy_runtime import make_prompt_fetcher

        fetcher = make_prompt_fetcher(policy_runtime)
    llm = _resolve_invoker(invoker, stage="background", policy_runtime=policy_runtime)
    if policy_runtime is not None:
        from libs.sbar.policy_runtime import stage_llm_params

        llm_params = stage_llm_params(policy_runtime, "background")
    else:
        llm_params = {"max_tokens": 1024, "temperature": 0.0}
    system_map = fetcher(_PROMPT_NAME_BACKGROUND)
    partitions, partition_report = partition_background_sources(
        sources,
        codes,
        referring_specialty=referring_specialty,
        coverage=coverage,
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
                    "record_count": len({d.source_id for d in partition.descriptors}),
                    "status": "started",
                }
            )
        result = await _invoke_background_part(
            partition,
            system=system_map,
            invoker=llm,
            patient_id=patient_id,
            llm_params=llm_params,
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

    # Single-partition path: behave like the legacy single-call
    # Background -- no notice, no part heading, just return the
    # one part's markdown directly.
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

    # Multi-partition path: deterministic stitch, always. Each part
    # renders under its own heading; failed parts render as a
    # "this part did not finish" placeholder so the gap is visible
    # in the rendered Background rather than silently swallowed.
    stitched = _stitch_partials_deterministic(part_results)
    error_message: str | None = None
    error_code: str | None = None
    if failed_parts:
        friendly = translate_error("background", "background_part_failed")
        error_message = friendly["message"]
        error_code = friendly["code"]

    return {
        **base_response,
        "markdown": stitched,
        "raw": {},
        "error": error_message,
        "error_code": error_code,
        "parts": parts_summary,
    }


async def call_recall(
    *,
    registry: Any,
    budget: Any,
    preflight_reasons: list[str],
    allowed_chunk_ids: list[str],
    run_id: str = "",
    patient_id: str = "",
    prompt_fetcher: PromptFetcher | None = None,
    policy_runtime: Any | None = None,
    converse_fn: Callable[..., Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    """Run the bounded recall tool loop under manifest policy."""
    from libs.sbar.recall_loop import run_recall_loop

    fetcher = _resolve_prompt_fetcher(prompt_fetcher)
    if policy_runtime is not None and prompt_fetcher is None:
        from libs.sbar.policy_runtime import make_prompt_fetcher

        fetcher = make_prompt_fetcher(policy_runtime)
    try:
        system = fetcher(_PROMPT_NAME_RECALL)
    except RuntimeError:
        from libs.prompts.sbar_recall_v1 import SBAR_RECALL_SYSTEM_V1

        system = SBAR_RECALL_SYSTEM_V1
    provider = "aws"
    tier = "big"
    if policy_runtime is not None:
        provider = str(getattr(policy_runtime, "model_provider", None) or provider)
        tier = str(getattr(policy_runtime, "model_tier", None) or tier)

    result = await run_recall_loop(
        registry=registry,
        budget=budget,
        preflight_reasons=preflight_reasons,
        allowed_chunk_ids=allowed_chunk_ids,
        run_id=run_id,
        system_prompt=system,
        patient_id=patient_id,
        provider=provider,
        tier=tier,
        converse_fn=converse_fn,
    )
    exhaustion = result.exhaustion
    return {
        "evidence": result.evidence,
        "exhaustion": exhaustion,
        "missing": list(result.missing or []),
        "llm_calls": result.llm_calls,
        "audit_log": list(result.audit_log or []),
        "raw": dict(result.raw or {}),
        "error": None if result.evidence or not exhaustion else "recall_incomplete",
        "error_code": (
            None if result.evidence or not exhaustion else "recall_budget_exhausted"
        ),
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
    prompt_fetcher: PromptFetcher | None = None,
    invoker: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    policy_runtime: Any | None = None,
) -> dict[str, Any]:
    fetcher = _resolve_prompt_fetcher(prompt_fetcher)
    if policy_runtime is not None and prompt_fetcher is None:
        from libs.sbar.policy_runtime import make_prompt_fetcher, stage_llm_params

        fetcher = make_prompt_fetcher(policy_runtime)
    llm = _resolve_invoker(
        invoker, stage="recommendation", policy_runtime=policy_runtime
    )
    llm_params = (
        stage_llm_params(policy_runtime, "recommendation")
        if policy_runtime is not None
        else {"max_tokens": 1024, "temperature": 0.0}
    )
    system = fetcher(_PROMPT_NAME_RECOMMENDATION)
    user = _serialise_recommendation_context(
        situation_md=situation_md,
        background_md=background_md,
        assessment_md=assessment_md,
        assessment_rules=assessment_rules,
        guideline_titles=guideline_titles,
        guidelines=guidelines,
    )
    raw = await llm(
        system,
        user,
        max_tokens=int(llm_params.get("max_tokens") or 1024),
        temperature=float(llm_params.get("temperature") or 0.0),
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
