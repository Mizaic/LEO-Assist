"""Encounter-level and batch runner for the cohort annotation pipeline.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Usage:
    from libs.cohort_annotation.runner import annotate_encounter, annotate_batch

    # single encounter (blocking)
    result = annotate_encounter(encounter_row)

    # batch (thread-pool)
    results = annotate_batch(encounter_rows, max_workers=8)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Maximum wall-clock seconds allowed for a single encounter.  Protects against
# a hanging Bedrock TCP connection that has no bytes flowing but the SSL/urllib3
# socket timeout hasn't fired (can happen inside nested ThreadPoolExecutor threads
# on some botocore/urllib3 configurations).
_ENCOUNTER_TIMEOUT_S = 120  # ReadTimeoutError is no longer retried, so worst case is one
                            # 90s read timeout + graph overhead. 120s catches anything stuck
                            # beyond that without burning 6 minutes per encounter.

# Lazy-compiled graph to avoid import overhead in test environments
_COMPILED_GRAPH: Any = None


def _get_graph() -> Any:
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        from libs.cohort_annotation.graph import build_graph
        _COMPILED_GRAPH = build_graph()
    return _COMPILED_GRAPH


@dataclass
class AnnotationResult:
    patient_id: str
    encounter_id: str
    encounter_date: str
    encounter_class: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    qa_drops: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    annotation_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "patient_id":            self.patient_id,
            "encounter_id":          self.encounter_id,
            "encounter_date":        self.encounter_date,
            "encounter_class":       self.encounter_class,
            "entities":              self.entities,
            "relations":             self.relations,
            "qa_drops":              self.qa_drops,
            "errors":                self.errors,
            "llm_calls":             self.llm_calls,
            "total_input_tokens":    self.total_input_tokens,
            "total_output_tokens":   self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "annotation_complete":   self.annotation_complete,
        }


def annotate_encounter(
    encounter_row: dict[str, Any],
    *,
    progress_callback: Callable[[str, str], None] | None = None,
) -> AnnotationResult:
    """Annotate a single encounter row from the JSONL export.

    Args:
        encounter_row: a dict from data/cancer_cohort/p*.jsonl.
        progress_callback: optional (patient_id, encounter_id) -> None.
    """
    pid = str(encounter_row.get("patient_id") or "")
    eid = str(encounter_row.get("encounter_id") or "")
    date = str(encounter_row.get("encounter_date") or "")

    initial_state: dict[str, Any] = {
        "patient_id":              pid,
        "encounter_id":            eid,
        "encounter_date":          date,
        "encounter_flags":         encounter_row.get("encounter_flags") or "",
        "text":                    encounter_row.get("text") or "",
        "sentences":               encounter_row.get("sentences") or [],
        "existing_coded_concepts": encounter_row.get("existing_coded_concepts") or [],
        "patient_context":         encounter_row.get("patient_context") or {},
        "structured_entities":     [],
        "structured_missing":      [],
        "narrative_entities":      [],
        "entities":                [],
        "relations":               [],
        "qa_drops":                [],
        "errors":                  [],
        "retry_count":             0,
        "llm_calls":               0,
        "total_input_tokens":      0,
        "total_output_tokens":     0,
        "total_cache_read_tokens": 0,
        "annotation_complete":     False,
    }

    graph = _get_graph()
    try:
        # Each encounter gets its own single-thread pool so a zombie thread
        # from a timed-out call cannot block any other encounter.  The pool is
        # released immediately on success; on timeout shutdown(wait=False) lets
        # the zombie drain in the background without blocking new encounters.
        _graph_pool = ThreadPoolExecutor(max_workers=1)
        _fut = _graph_pool.submit(graph.invoke, initial_state)
        try:
            final_state = _fut.result(timeout=_ENCOUNTER_TIMEOUT_S)
            _graph_pool.shutdown(wait=False)
        except FuturesTimeoutError:
            _graph_pool.shutdown(wait=False)
            msg = (
                f"encounter timed out after {_ENCOUNTER_TIMEOUT_S}s "
                f"(graph.invoke did not complete)"
            )
            logger.warning("graph timed out for %s/%s — %s", pid, eid, msg)
            return AnnotationResult(
                patient_id=pid,
                encounter_id=eid,
                encounter_date=date,
                encounter_class="ERROR",
                errors=[msg],
            )
    except Exception as exc:
        logger.error("graph failed for encounter %s/%s: %s", pid, eid, exc)
        return AnnotationResult(
            patient_id=pid,
            encounter_id=eid,
            encounter_date=date,
            encounter_class="ERROR",
            errors=[str(exc)],
        )

    if progress_callback:
        try:
            progress_callback(pid, eid)
        except Exception:
            pass

    return AnnotationResult(
        patient_id=pid,
        encounter_id=eid,
        encounter_date=date,
        encounter_class=final_state.get("encounter_class") or "UNKNOWN",
        entities=final_state.get("entities") or [],
        relations=final_state.get("relations") or [],
        qa_drops=final_state.get("qa_drops") or [],
        errors=final_state.get("errors") or [],
        llm_calls=final_state.get("llm_calls") or 0,
        total_input_tokens=final_state.get("total_input_tokens") or 0,
        total_output_tokens=final_state.get("total_output_tokens") or 0,
        total_cache_read_tokens=final_state.get("total_cache_read_tokens") or 0,
        annotation_complete=bool(final_state.get("annotation_complete")),
    )


def annotate_batch(
    encounter_rows: list[dict[str, Any]],
    *,
    max_workers: int = 8,
    progress_callback: Callable[[str, str], None] | None = None,
) -> list[AnnotationResult]:
    """Annotate multiple encounters in parallel using a thread pool.

    Returns results in the same order as encounter_rows.
    """
    results: list[AnnotationResult | None] = [None] * len(encounter_rows)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(annotate_encounter, row, progress_callback=progress_callback): i
            for i, row in enumerate(encounter_rows)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:
                row = encounter_rows[idx]
                logger.error(
                    "batch worker failed for encounter %s: %s",
                    row.get("encounter_id"),
                    exc,
                )
                results[idx] = AnnotationResult(
                    patient_id=str(row.get("patient_id") or ""),
                    encounter_id=str(row.get("encounter_id") or ""),
                    encounter_date=str(row.get("encounter_date") or ""),
                    encounter_class="ERROR",
                    errors=[str(exc)],
                )

    return [r for r in results if r is not None]
