"""Token-budgeted window-local LLM extraction orchestration.

Atlas trace:
  DO: DO-292D7D75
  DI: DI-452DA083, DI-8A2F4DAB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-292D7D75")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from libs.nlp.sentence_splitter import SentenceChunk

logger = logging.getLogger(__name__)

RunLlmExtraction = Callable[..., dict[str, Any]]

INCOMPLETE_EXTRACTION_WARNING = "extraction_incomplete"


@dataclass
class _WindowRun:
    llm_by_id: dict[str, SentenceChunk]
    orig_by_id: dict[str, SentenceChunk]
    encounter_text: str
    state: dict[str, Any]
    context_mode: str
    max_window_input_tokens: int
    run_llm_extraction: RunLlmExtraction


def extraction_window_policy(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return extraction window policy from pinned manifest, if present."""
    from libs.pipeline.extraction_prompt import normalise_context_mode

    manifest = state.get("execution_manifest") or {}
    extraction = manifest.get("extraction") or {}
    if not extraction:
        return None
    return {
        "window_size": int(extraction.get("windowSize") or 10),
        "window_overlap": int(extraction.get("windowOverlap") or 1),
        "context_mode": normalise_context_mode(extraction.get("contextMode")),
        "max_window_input_tokens": int(extraction.get("maxWindowInputTokens") or 16000),
    }


def normalise_chunks_for_llm(
    chunks: list[SentenceChunk],
    *,
    skip: bool = False,
) -> list[SentenceChunk]:
    """Copy chunks with form-checkbox normalisation for LLM input only.

    Pass ``skip=True`` for a taught form. Its text was already normalised
    by its own :FormSchema, and the generic rules would cut the free-text
    clinical narrative out of it.
    """
    if skip:
        return list(chunks)
    from libs.ner.form_checkbox_normalizer import normalize_form_checkbox_text

    return [
        SentenceChunk(
            sentence_id=c.sentence_id,
            text=normalize_form_checkbox_text(str(c.text or "")),
            start=c.start,
            end=c.end,
        )
        for c in chunks
    ]


def _build_window_context(
    window_llm_chunks: list[SentenceChunk],
    *,
    truncated: bool,
    max_window_input_tokens: int,
    window_index: int,
    chunk_ids: tuple[str, ...],
) -> tuple[str, bool]:
    from libs.pipeline.document_chunk_loader import CHUNK_TEXT_SEPARATOR
    from libs.pipeline.extraction_window import truncate_text_to_token_budget

    window_context = CHUNK_TEXT_SEPARATOR.join(
        str(c.text or "") for c in window_llm_chunks
    )
    if not truncated:
        return window_context, False
    headroom = max(200, max_window_input_tokens // 2)
    window_context = truncate_text_to_token_budget(window_context, headroom)
    logger.warning(
        "extraction_window_truncated=true window_index=%s chunk_ids=%s",
        window_index,
        list(chunk_ids),
    )
    return window_context, True


def _window_model_fields(
    current: dict[str, Any],
    partial: dict[str, Any],
) -> dict[str, Any]:
    """Keep the first window's live model identity for the inspector."""
    if str(current.get("extraction_model_name") or "").strip():
        return current
    keys = (
        "extraction_model_name",
        "extraction_model_version",
        "extraction_model_requested_version",
        "extraction_model_version_mismatch",
    )
    return {key: partial[key] for key in keys if key in partial}


def _accumulate_window_tokens(
    merged_tokens: dict[str, Any],
    tokens: dict[str, Any],
) -> None:
    merged_tokens["input_tokens"] += int(tokens.get("input_tokens") or 0)
    merged_tokens["output_tokens"] += int(tokens.get("output_tokens") or 0)
    merged_tokens["cached_tokens"] += int(tokens.get("cached_tokens") or 0)
    merged_tokens["cost_usd"] = round(
        float(merged_tokens["cost_usd"]) + float(tokens.get("cost_usd") or 0.0),
        6,
    )


def _empty_token_bucket() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
    }


def _slice_window_chunks(
    window: Any, chunks: list[SentenceChunk]
) -> list[SentenceChunk]:
    """Narrow each chunk to the part this window covers.

    An oversized chunk is split across several windows, so a window must be
    shown only its own slice. Offsets stay in document coordinates so span
    resolution still lands in the right place.
    """
    text_slice = getattr(window, "text_slice", None)
    if text_slice is None:
        return chunks
    start, end = text_slice
    sliced: list[SentenceChunk] = []
    for chunk in chunks:
        if window.chunk_ids != (str(chunk.sentence_id or ""),):
            sliced.append(chunk)
            continue
        part = str(chunk.text or "")[start:end]
        sliced.append(
            SentenceChunk(
                sentence_id=chunk.sentence_id,
                text=part,
                start=chunk.start + start,
                end=chunk.start + start + len(part),
            )
        )
    return sliced


def _run_one_window(
    window: Any,
    ctx: _WindowRun,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Return (partial, error, truncated) for one extraction window."""
    from libs.pipeline.extraction_prompt import CONTEXT_MODE_WINDOW_LOCAL

    window_llm_chunks = _slice_window_chunks(
        window,
        [ctx.llm_by_id[cid] for cid in window.chunk_ids if cid in ctx.llm_by_id],
    )
    window_orig_chunks = _slice_window_chunks(
        window,
        [ctx.orig_by_id[cid] for cid in window.chunk_ids if cid in ctx.orig_by_id],
    )
    if not window_llm_chunks:
        return None, None, False
    window_context, was_truncated = _build_window_context(
        window_llm_chunks,
        truncated=window.truncated,
        max_window_input_tokens=ctx.max_window_input_tokens,
        window_index=window.index,
        chunk_ids=window.chunk_ids,
    )
    llm_context = (
        window_context
        if ctx.context_mode == CONTEXT_MODE_WINDOW_LOCAL
        else ctx.encounter_text
    )
    try:
        partial = ctx.run_llm_extraction(
            llm_context,
            window_llm_chunks,
            ctx.state,
            span_document_text=ctx.encounter_text,
            span_sentences=window_orig_chunks,
            context_mode=ctx.context_mode,
        )
    except Exception as exc:
        logger.exception(
            "extraction_window_failed window_index=%s chunk_ids=%s",
            window.index,
            list(window.chunk_ids),
        )
        err = f"extraction_window_failed index={window.index}: {exc}"
        return None, err, was_truncated
    return partial, None, was_truncated


def _record_window_partial(
    window: Any,
    partial: dict[str, Any],
    *,
    window_outputs: list[list[dict[str, Any]]],
    usages: list[Any],
    merged_tokens: dict[str, Any],
    model_fields: dict[str, Any],
) -> dict[str, Any]:
    from libs.pipeline.extraction_window import WindowUsage

    window_outputs.append(list(partial.get("entities") or []))
    tokens = dict(partial.get("llm_tokens") or {})
    usages.append(
        WindowUsage(
            window_index=window.index,
            input_tokens=int(tokens.get("input_tokens") or 0),
            output_tokens=int(tokens.get("output_tokens") or 0),
            cache_read_tokens=int(tokens.get("cached_tokens") or 0),
            cost_usd=float(tokens.get("cost_usd") or 0.0),
        )
    )
    _accumulate_window_tokens(merged_tokens, tokens)
    return _window_model_fields(model_fields, partial)


def run_windowed_llm_extraction(
    encounter_text: str,
    chunks: list[SentenceChunk],
    state: dict[str, Any],
    *,
    window_size: int,
    window_overlap: int,
    context_mode: str,
    max_window_input_tokens: int,
    run_llm_extraction: RunLlmExtraction,
    span_chunks: list[SentenceChunk] | None = None,
) -> dict[str, Any]:
    """Run LLM extraction in token-budgeted windows and merge entities."""
    from libs.pipeline.extraction_window import (
        ChunkRef,
        aggregate_window_usage,
        merge_window_entities,
        plan_extraction_windows_by_tokens,
    )
    from libs.pipeline.form_schema_store import has_taught_form_schema

    llm_chunks = normalise_chunks_for_llm(
        chunks,
        skip=has_taught_form_schema(state),
    )
    span_source = span_chunks if span_chunks is not None else chunks
    chunk_refs = [
        ChunkRef(chunk_id=str(c.sentence_id or ""), text=str(c.text or ""))
        for c in llm_chunks
    ]
    windows = plan_extraction_windows_by_tokens(
        chunk_refs,
        max_window_input_tokens=max_window_input_tokens,
        window_overlap_chunks=window_overlap,
        max_chunks_per_window=window_size,
    )
    ctx = _WindowRun(
        llm_by_id={str(c.sentence_id or ""): c for c in llm_chunks},
        orig_by_id={str(c.sentence_id or ""): c for c in span_source},
        encounter_text=encounter_text,
        state=state,
        context_mode=context_mode,
        max_window_input_tokens=max_window_input_tokens,
        run_llm_extraction=run_llm_extraction,
    )
    logger.info(
        "extraction_window_plan context_mode=%s window_count=%s "
        "max_window_input_tokens=%s",
        context_mode,
        len(windows),
        max_window_input_tokens,
    )
    collected = _collect_windows(windows, ctx)
    collected["merged_tokens"]["window_usage"] = aggregate_window_usage(
        collected["usages"]
    )
    window_sims = collected["window_similarities"]
    result: dict[str, Any] = {
        "entities": merge_window_entities(collected["window_outputs"]),
        "llm_tokens": collected["merged_tokens"],
        "extraction_route": "llm-windowed",
        "extraction_context_mode": context_mode,
        "extraction_window_count": len(windows),
        "extraction_window_truncated_count": collected["truncated_windows"],
        "extraction_windows_completed": collected["completed"],
        "few_shot_max_similarity": min(window_sims) if window_sims else None,
        **collected["model_fields"],
    }
    result.update(
        _incomplete_extraction_fields(
            planned=len(windows),
            completed=collected["completed"],
            truncated_windows=collected["truncated_windows"],
        )
    )
    if collected["errors"]:
        result["errors"] = collected["errors"]
    return result


def _incomplete_extraction_fields(
    *, planned: int, completed: int, truncated_windows: int
) -> dict[str, Any]:
    """Mark a run that did not read the whole letter.

    Findings in the unread part come back absent, and absent reads as "not
    present". Failing to look and finding nothing must not produce the same
    output, so a short read is stated rather than left to be inferred from
    what is missing.
    """
    unread = max(0, planned - completed)
    if not unread and not truncated_windows:
        return {}
    reasons: list[str] = []
    if unread:
        reasons.append(f"{unread} of {planned} parts of the letter were not read")
    if truncated_windows:
        reasons.append(f"{truncated_windows} part(s) were too long to read in full")
    return {
        "extraction_partial": True,
        "warnings": [
            f"{INCOMPLETE_EXTRACTION_WARNING}: a person needs to check this "
            f"referral against the letter. We did not read all of it: "
            f"{'; '.join(reasons)}. Some findings may be missing."
        ],
    }


def _collect_windows(windows: list[Any], ctx: _WindowRun) -> dict[str, Any]:
    """Run each window and keep facts already found if a later window fails."""
    window_outputs: list[list[dict[str, Any]]] = []
    usages: list[Any] = []
    merged_tokens = _empty_token_bucket()
    truncated_windows = 0
    completed = 0
    model_fields: dict[str, Any] = {}
    errors: list[str] = []
    window_similarities: list[float] = []
    for window in windows:
        partial, error, was_truncated = _run_one_window(window, ctx)
        if was_truncated:
            truncated_windows += 1
        if error:
            errors.append(error)
            break
        completed += 1
        if partial is None:
            continue
        model_fields = _record_window_partial(
            window,
            partial,
            window_outputs=window_outputs,
            usages=usages,
            merged_tokens=merged_tokens,
            model_fields=model_fields,
        )
        sim = partial.get("few_shot_max_similarity")
        if isinstance(sim, (int, float)):
            window_similarities.append(float(sim))
    return {
        "window_outputs": window_outputs,
        "usages": usages,
        "merged_tokens": merged_tokens,
        "truncated_windows": truncated_windows,
        "completed": completed,
        "model_fields": model_fields,
        "errors": errors,
        "window_similarities": window_similarities,
    }
