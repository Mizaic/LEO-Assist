"""Post-processing subgraph wrapping the canonical 9-layer pipeline.

When the stack cannot run, this subgraph degrades the run instead of
handing the raw entities on. The raw entities have not been through the
negation guard or the scope guard, so passing them off as processed
output would show a clinician unchecked text as checked text. See
.cursor/rules/fail-closed-boundary.mdc rule 1.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F (degraded runs routed to human review)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.ner.context_span_resolution import UNRESOLVED_KEY

logger = logging.getLogger(__name__)

# Read by a person triaging the run, so it says what happened and what to
# do next. Prefixed with a machine code like the other pipeline warnings.
POST_PROCESSING_FAILED_WARNING = (
    "post_processing_failed: LEO's safety checks did not run on this "
    "referral. A person needs to check it before it is used."
)

# Machine code first so the run can be filtered on it, then the plain-English
# sentence a person triaging the run actually reads.
UNRESOLVED_SPAN_WARNING = "assertion_not_checked"


def _unresolved_span_warnings(entities: list[dict[str, Any]]) -> list[str]:
    """Announce facts LEO could not find in the letter, if there are any.

    ConText is skipped for a fact whose words are nowhere in the letter,
    so its assertion stays whatever the extractor guessed -- and the
    extractor guesses "present". Marking the fact is not enough on its own:
    a log line cannot be read from the patient record, so the count has to
    reach the run. See .cursor/rules/fail-closed-boundary.mdc rule 1.
    """
    count = sum(1 for e in entities if e.get(UNRESOLVED_KEY))
    if not count:
        return []
    return [
        f"{UNRESOLVED_SPAN_WARNING}: LEO could not find {count} of "
        f"{len(entities)} findings in the letter, so it could not check "
        f"whether they were ruled out. A person needs to read these."
    ]


class PostProcessingState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    enable_disorder_gate: bool
    coding_mode: str
    org_id: str
    local_concept_patterns: list[Any]
    processed_entities: list[dict[str, Any]]
    post_processing_trace: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]
    degraded: bool


def _resolve_local_patterns(state: PostProcessingState) -> list[Any]:
    """Use injected patterns, else load active package patterns for org_id."""
    injected = state.get("local_concept_patterns")
    if injected is not None:
        return list(injected or [])
    org_id = str(state.get("org_id") or "").strip() or None
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.ner.local_concept_recovery import load_active_package_patterns

        client = KnowledgeGraphClient()
        try:
            return load_active_package_patterns(client, org_id)
        finally:
            client.close()
    except Exception:
        logger.debug("active local package pattern load skipped", exc_info=True)
        return []


def _run_layers(
    state: PostProcessingState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Call the canonical post-processing stack for this state."""
    from libs.ner.post_processor_rules import parse_rules
    from libs.pipeline.post_processing import run_post_processing_with_trace

    raw_rules = state.get("rules") or []
    return run_post_processing_with_trace(
        state.get("encounter_text") or "",
        state.get("entities") or [],
        rules=parse_rules(raw_rules) if raw_rules else None,
        enable_disorder_gate=state.get("enable_disorder_gate", False),
        coding_mode=state.get("coding_mode", "hitl"),
        local_concept_patterns=_resolve_local_patterns(state),
    )


def _error_trace(exc: Exception, before_count: int) -> dict[str, Any]:
    """One trace row saying the whole stack failed."""
    return {
        "layer_id": "post_processing",
        "name": "Post-processing",
        "status": "error",
        "error": str(exc),
        "before_count": before_count,
        "after_count": 0,
        "added_count": 0,
        "removed_count": before_count,
        "updated_count": 0,
        "duration_ms": 0,
    }


def _degraded_result(
    state: PostProcessingState,
    errors: list[str],
    exc: Exception,
) -> dict[str, Any]:
    """Return a state that carries the failure instead of hiding it.

    The entities are dropped on purpose. They never reached the negation
    guard or the scope guard, so handing them on as ``processed_entities``
    would present unchecked output as checked output.
    """
    warnings = list(state.get("warnings") or [])
    if POST_PROCESSING_FAILED_WARNING not in warnings:
        warnings.append(POST_PROCESSING_FAILED_WARNING)
    return {
        "entities": [],
        "processed_entities": [],
        "post_processing_trace": [_error_trace(exc, len(state.get("entities") or []))],
        "errors": [*errors, f"post_processing: {exc}"],
        "warnings": warnings,
        "degraded": True,
    }


def run_post_process(state: PostProcessingState) -> dict[str, Any]:
    """Run every post-processing layer, or degrade the run if one fails."""
    errors = list(state.get("errors") or [])
    try:
        processed, layer_trace = _run_layers(state)
    except ImportError as exc:
        logger.warning("Post-processing module unavailable: %s", exc)
        return _degraded_result(state, errors, exc)
    except Exception as exc:
        logger.exception("Post-processing failed")
        return _degraded_result(state, errors, exc)

    warnings = list(state.get("warnings") or [])
    for warning in _unresolved_span_warnings(processed):
        if warning not in warnings:
            warnings.append(warning)
    unresolved = any(e.get(UNRESOLVED_KEY) for e in processed)

    return {
        "entities": processed,
        "processed_entities": processed,
        "post_processing_trace": layer_trace,
        "errors": errors,
        "warnings": warnings,
        "degraded": bool(state.get("degraded")) or unresolved,
    }


def build_post_processing_subgraph() -> CompiledStateGraph:
    g = StateGraph(PostProcessingState)
    g.add_node("run_post_process", run_post_process)
    g.add_edge(START, "run_post_process")
    g.add_edge("run_post_process", END)
    return g.compile()
