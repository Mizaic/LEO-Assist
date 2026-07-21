"""AI Draft Assistant for the audit template builder -- multi-phase flow.

Atlas trace:
  DO: DO-3775670C
  DI: DI-64CA7740
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3775670C")

Endpoint:
  POST /audit-templates/draft

Phases (controlled by the ``phase`` field in the request body):

  intent    -- LLM is forced to call ``gather_requirements``.
               Returns a ``questions-available`` SSE event with 5-10 MCQ
               questions so the frontend can render an interactive Q&A card.

  discover  -- LLM receives the user answers and the full conversation, then
               is forced to call ``propose_dashboard``.
               Returns a ``plan-available`` SSE event with the tile plan.

  build     -- No LLM call. Validates the approved tile list against the
               live catalogue and returns one ``tile-added`` event per tile,
               then a ``build-complete`` summary.

SSE event types:
  text-delta          -- streaming narration token
  questions-available -- { questions: [...] }  (intent phase)
  plan-available      -- { rationale, tiles, warnings } (discover phase)
  tile-added          -- { tile } (build phase)
  build-complete      -- { added, skipped, warnings } (build phase)
  finish              -- stream complete
  error               -- unexpected failure

Prompt injection protection:
  Every user message is passed through ``_sanitise_user_input()`` before
  being inserted into the LLM message list. This strips XML/SGML tags and
  rejects known role-injection patterns.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.audit_metric_queries import get_catalogue

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DraftMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DraftRequest(BaseModel):
    messages: list[DraftMessage]
    phase: Literal["intent", "discover", "build"] = "intent"
    answers: dict[str, str] = {}
    approved_tiles: list[dict[str, Any]] = []
    approved_pages: list[dict[str, Any]] = []
    zone1_narrative: str = ""
    zone2_narrative: str = ""
    current_tiles: list[dict[str, Any]] = []
    existing_metric_ids: list[str] = []


# Keep in sync with services/ui/src/lib/auditTemplateApi.ts WIDGET_CATALOGUE
_VALID_WIDGETS: frozenset[str] = frozenset(
    {
        "symptoms_ppv",
        "blood_signal",
        "cancer_type",
        "cancer_stage",
        "diagnostic_intervals",
        "consultations",
        "safety_netting",
        "investigations",
        "avoidable_delays",
        "care_obstructions",
        "place_of_presentation",
        "demographics",
        "comorbidities",
    }
)


# ---------------------------------------------------------------------------
# Prompt injection protection
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"(\n\s*(Human|Assistant|System)\s*:)"
    r"|(<\s*/?\s*(system|human|assistant|inst|s)\s*>)"
    r"|(\[INST\]|<<SYS>>|</s>)",
    re.IGNORECASE,
)

_MAX_INPUT_LEN = 2000


def _sanitise_user_input(text: str) -> str:
    """Strip injection patterns from user-supplied text.

    Removes XML/SGML role tags, truncates to 2000 characters, and replaces
    known role-injection markers with a safe stub. Logs a warning when any
    suspicious pattern is detected.
    """
    truncated = text[:_MAX_INPUT_LEN]
    stripped = re.sub(r"<[^>]{0,120}>", "", truncated)
    if _INJECTION_PATTERNS.search(stripped):
        logger.warning("audit_draft: prompt injection attempt detected, sanitising")
        stripped = _INJECTION_PATTERNS.sub(" [redacted] ", stripped)
    return stripped.strip()


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_GATHER_REQUIREMENTS_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "gather_requirements",
        "description": (
            "Analyse the user's intent and return 5-10 multiple-choice questions "
            "to clarify what they need. Always call this tool -- never respond "
            "with plain text only."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "intent_summary": {
                        "type": "string",
                        "description": (
                            "One sentence summarising what the user wants "
                            "to achieve with this dashboard."
                        ),
                    },
                    "questions": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "question": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "label": {"type": "string"},
                                            "recommended": {"type": "boolean"},
                                        },
                                        "required": ["id", "label", "recommended"],
                                    },
                                },
                            },
                            "required": ["id", "question", "options"],
                        },
                    },
                },
                "required": ["intent_summary", "questions"],
            }
        },
    }
}

_PROPOSE_DASHBOARD_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "propose_dashboard",
        "description": (
            "Propose a set of dashboard tiles based on the user requirements "
            "and their answers. Always call this tool -- never respond with "
            "plain text only."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "rationale": {
                        "type": "string",
                        "description": (
                            "2-3 sentences explaining the overall design choices "
                            "and how they address the user's needs."
                        ),
                    },
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page_id": {"type": "string"},
                                "label": {"type": "string"},
                                "kind": {
                                    "type": "string",
                                    "description": "snapshot or report",
                                },
                            },
                            "required": ["page_id", "label"],
                        },
                        "description": "Named report pages/tabs for the draft.",
                    },
                    "tiles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric_id": {"type": "string"},
                                "label": {"type": "string"},
                                "tile_type": {"type": "string"},
                                "section": {"type": "string"},
                                "page_id": {
                                    "type": "string",
                                    "description": "Target page_id from pages[].",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": (
                                        "One sentence explaining why this tile "
                                        "was chosen."
                                    ),
                                },
                                "story_headline": {
                                    "type": "string",
                                    "description": (
                                        "Optional one-sentence DataPOV for this "
                                        "tile (e.g. 'Breast cancer accounts for "
                                        "34% of referrals')."
                                    ),
                                },
                                "highlight_key": {
                                    "type": "string",
                                    "description": (
                                        "Optional: the category value to "
                                        "emphasise with a contrasting colour."
                                    ),
                                },
                            },
                            "required": ["metric_id", "label", "tile_type", "reason"],
                        },
                    },
                    "zone1_narrative": {
                        "type": "string",
                        "description": "Optional Zone 1 scorecard narrative.",
                    },
                    "zone2_narrative": {
                        "type": "string",
                        "description": "Optional Zone 2 priorities narrative.",
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Any caveats, e.g. 'blood_signal requires the GDS "
                            "enrichment pipeline'."
                        ),
                    },
                },
                "required": ["rationale", "tiles", "warnings"],
            }
        },
    }
}

_INTENT_TOOL_CONFIG: dict[str, Any] = {
    "tools": [_GATHER_REQUIREMENTS_TOOL],
    "toolChoice": {"tool": {"name": "gather_requirements"}},
}

_DISCOVER_TOOL_CONFIG: dict[str, Any] = {
    "tools": [_PROPOSE_DASHBOARD_TOOL],
    "toolChoice": {"tool": {"name": "propose_dashboard"}},
}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------


def _intent_system_prompt(catalogue: list[dict[str, Any]]) -> str:
    metric_list = "\n".join(
        f"  - {m['metric_id']}: {m['title']}"
        f" ({m['output_type']}) -- {m['description']}"
        for m in catalogue
    )
    return (
        "You are an expert NHS clinical audit architect helping a clinician or "
        "practice manager build an audit dashboard. Your first job is to "
        "understand what they need by calling the gather_requirements tool "
        "with 5-10 multiple-choice questions.\n\n"
        "Good questions cover:\n"
        "  - Primary audience (GP partner / practice manager / PCN board / ICB)\n"
        "  - Key focus area (cancer pathways / coding quality / safety netting / "
        "referral quality / demographics)\n"
        "  - Time horizon (last quarter / last year / rolling 3 years)\n"
        "  - Level of detail (executive summary KPIs / operational detail / "
        "full NCDA audit)\n"
        "  - Specific cancer types of interest (all / breast / colorectal / lung)\n"
        "  - Whether to include benchmark / target lines\n"
        "  - Whether to include specialised clinical signal widgets\n\n"
        "Always mark the most sensible default as recommended=true in each "
        "question's option list.\n\n"
        "Available metrics for reference:\n" + metric_list
    )


def _discover_system_prompt(
    catalogue: list[dict[str, Any]], answers: dict[str, str]
) -> str:
    metric_list = "\n".join(
        f"  - {m['metric_id']}: {m['title']}"
        f" ({m['output_type']}) -- {m['description']}"
        for m in catalogue
    )
    answers_text = (
        "\n".join(f"  {k}: {v}" for k, v in answers.items())
        if answers
        else "  (no answers provided)"
    )
    return (
        "You are an expert NHS clinical audit architect. Based on the user's "
        "requirements and the answers below, propose a well-structured dashboard "
        "by calling the propose_dashboard tool.\n\n"
        "User's answers to discovery questions:\n" + answers_text + "\n\n"
        "Design guidelines:\n"
        "  - Propose pages[] with page_id, label, and kind (snapshot or report).\n"
        "  - Assign each tile a page_id from pages[].\n"
        "  - Choose tile_type from: kpi_strip, bar_chart, line_chart, table, "
        "interval_plot, or widget (any WIDGET_CATALOGUE id).\n"
        "  - Group related tiles under a section name.\n"
        "  - Use only metric_id values from the catalogue below (or widget ids).\n"
        "  - Optionally draft zone1_narrative and zone2_narrative for the "
        "snapshot page.\n"
        "  - Where appropriate, suggest a story_headline (one-sentence DataPOV) "
        "and a highlight_key to emphasise the most important data point.\n"
        "  - Flag any tiles that need special infrastructure in warnings.\n\n"
        "Available metrics:\n" + metric_list
    )


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ---------------------------------------------------------------------------
# Build phase (no LLM)
# ---------------------------------------------------------------------------


def _build_phase(body: DraftRequest):
    """Validate approved tiles against the catalogue and emit add events."""
    catalogue = get_catalogue()
    valid_ids = {m["metric_id"] for m in catalogue}

    if body.approved_pages:
        yield _sse("pages-proposed", {"pages": body.approved_pages})

    if body.zone1_narrative or body.zone2_narrative:
        yield _sse(
            "narratives-proposed",
            {
                "zone1_narrative": body.zone1_narrative,
                "zone2_narrative": body.zone2_narrative,
            },
        )

    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for tile in body.approved_tiles:
        mid = tile.get("metric_id", "")
        if mid in valid_ids or mid in _VALID_WIDGETS:
            added.append(tile)
            yield _sse("tile-added", {"tile": tile})
        else:
            skipped.append({"metric_id": mid, "reason": "Unknown metric ID"})

    yield _sse(
        "build-complete",
        {
            "added": len(added),
            "skipped": skipped,
            "warnings": [],
        },
    )
    yield _sse("finish", {})


# ---------------------------------------------------------------------------
# LLM phase generator
# ---------------------------------------------------------------------------


def _llm_phase(
    body: DraftRequest,
    system: str,
    tool_config: dict[str, Any],
    result_event: str,
):
    """Run an LLM streaming call and map tool_use to a named SSE event."""
    from libs.llm_client.factory import create_llm

    messages = []
    for m in body.messages:
        clean = _sanitise_user_input(m.content) if m.role == "user" else m.content
        messages.append({"role": m.role, "content": clean})

    if not messages:
        yield _sse("error", {"message": "No messages provided"})
        return

    llm = create_llm(tier="small")

    for chunk in llm.converse_stream(
        system=system,
        messages=messages,
        max_tokens=2048,
        temperature=0.3,
        tool_config=tool_config,
        agent_task="audit_draft_assistant",
    ):
        chunk_type = chunk.get("type", "")

        if chunk_type == "text_delta":
            yield _sse("text-delta", {"delta": chunk.get("delta", "")})

        elif chunk_type == "tool_use":
            tool_input = chunk.get("input") or {}
            yield _sse(result_event, {"input": tool_input})

        elif chunk_type == "finish":
            yield _sse("finish", {})
            return

        elif chunk_type == "error":
            logger.error("audit_draft.stream_error: %s", chunk.get("message", ""))
            yield _sse("error", {"message": chunk.get("message", "LLM error")})
            return

    yield _sse("finish", {})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/audit-templates/draft")
def draft_template(
    body: DraftRequest,
    _scope: CallerScope = Depends(get_caller_scope),
) -> StreamingResponse:
    """Multi-phase AI dashboard builder.

    Phase ``intent``   -- returns questions-available SSE event.
    Phase ``discover`` -- returns plan-available SSE event.
    Phase ``build``    -- validates and streams tile-added / build-complete.
    """

    def _generate():
        try:
            if body.phase == "build":
                yield from _build_phase(body)
                return

            catalogue = get_catalogue()

            if body.phase == "intent":
                system = _intent_system_prompt(catalogue)
                yield from _llm_phase(
                    body, system, _INTENT_TOOL_CONFIG, "questions-available"
                )

            elif body.phase == "discover":
                system = _discover_system_prompt(catalogue, body.answers)
                yield from _llm_phase(
                    body, system, _DISCOVER_TOOL_CONFIG, "plan-available"
                )

            else:
                yield _sse("error", {"message": f"Unknown phase: {body.phase}"})

        except Exception as exc:
            logger.exception("audit_draft.generate_failed")
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
