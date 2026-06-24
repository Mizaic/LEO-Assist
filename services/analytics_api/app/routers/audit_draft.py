"""AI Draft Assistant for the audit template builder.

Provides a single POST endpoint that accepts a multi-turn conversation and
returns a server-sent event (SSE) stream. The LLM is forced to call the
`design_report` tool so the response is always structured tile suggestions.

Atlas trace:
  DO: DO-3775670C
  DI: DI-64CA7740

Endpoint:
  POST /audit-templates/draft   -- single LLM call, SSE response

SSE event types:
  text-delta              -- streaming narration from the LLM
  tool-input-available    -- the design_report tool call payload (tiles array)
  finish                  -- stream is complete
  error                   -- unexpected failure
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.audit_metric_queries import get_catalogue

logger = logging.getLogger(__name__)

from fastapi import APIRouter

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DraftMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DraftRequest(BaseModel):
    messages: list[DraftMessage]
    current_tiles: list[dict[str, Any]] = []
    existing_metric_ids: list[str] = []


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

_DESIGN_REPORT_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "design_report",
        "description": (
            "Add tiles to the audit template based on the user request. "
            "Always call this tool -- never respond with plain text only."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "rationale": {
                        "type": "string",
                        "description": "One or two sentences explaining the tile choices.",
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
                            },
                            "required": ["metric_id", "label", "tile_type"],
                        },
                    },
                },
                "required": ["rationale", "tiles"],
            }
        },
    }
}

_TOOL_CONFIG: dict[str, Any] = {
    "tools": [_DESIGN_REPORT_TOOL],
    "toolChoice": {"tool": {"name": "design_report"}},
}

# ---------------------------------------------------------------------------
# Few-shot examples baked into the system prompt
# ---------------------------------------------------------------------------

_FEW_SHOT = """
Examples of good `design_report` responses:

User: "Draft me an NCDA audit dashboard"
tiles: [
  {"metric_id":"patient_count","label":"Total patients","tile_type":"kpi_strip"},
  {"metric_id":"episode_count_by_condition","label":"Episodes by cancer site","tile_type":"bar_chart"},
  {"metric_id":"referral_route_distribution","label":"Referral routes","tile_type":"bar_chart"},
  {"metric_id":"primary_care_interval","label":"Primary care interval","tile_type":"interval_plot"},
  {"metric_id":"diagnostic_interval","label":"Diagnostic interval","tile_type":"interval_plot"},
  {"metric_id":"cancer_stage_distribution","label":"Stage at diagnosis","tile_type":"bar_chart"}
]

User: "Show me referral quality metrics"
tiles: [
  {"metric_id":"referral_stt_rate","label":"Straight-to-test rate","tile_type":"kpi_strip","section":"Referral quality"},
  {"metric_id":"referral_guideline_compliance_rate","label":"NG12 compliance","tile_type":"kpi_strip","section":"Referral quality"},
  {"metric_id":"referral_alternative_pathway_rate","label":"Alternative pathway rate","tile_type":"kpi_strip","section":"Referral quality"},
  {"metric_id":"referral_completeness_rate","label":"Referral completeness","tile_type":"kpi_strip","section":"Referral quality"}
]

User: "Safety netting overview for the board"
tiles: [
  {"metric_id":"unactioned_alerts_by_age","label":"Unactioned alerts by age","tile_type":"bar_chart","section":"Safety"},
  {"metric_id":"alert_escalation_rate","label":"Escalation rate","tile_type":"kpi_strip","section":"Safety"},
  {"metric_id":"repeat_referral_patients","label":"Repeat referral patients","tile_type":"table","section":"Safety"}
]
"""


def _build_system_prompt(catalogue: list[dict[str, Any]]) -> str:
    metric_list = "\n".join(
        f"  - {m['metric_id']}: {m['title']} ({m['output_type']}) -- {m['description']}"
        for m in catalogue
    )
    return (
        "You are an expert NHS clinical audit architect. "
        "Your job is to design high-quality audit report templates for GP practices "
        "and cancer tracking teams using the available metric library. "
        "Always call the `design_report` tool with appropriate tiles. "
        "Choose tile_type from: kpi_strip, bar_chart, line_chart, table, interval_plot. "
        "Group related tiles under a section name. "
        "Only use metric_id values from the catalogue below.\n\n"
        "Available metrics:\n"
        + metric_list
        + "\n\n"
        + _FEW_SHOT
    )


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/audit-templates/draft")
def draft_template(
    body: DraftRequest,
    _scope: CallerScope = Depends(get_caller_scope),
) -> StreamingResponse:
    """Stream LLM tile suggestions for the audit template builder.

    Accepts a multi-turn conversation and the current tile state.
    Returns SSE with text-delta, tool-input-available, and finish events.
    """

    def _generate():
        try:
            from libs.llm_client.factory import create_llm

            catalogue = get_catalogue()
            system = _build_system_prompt(catalogue)

            current_summary = (
                ", ".join(t.get("metric_id", "") for t in body.current_tiles)
                if body.current_tiles
                else "none"
            )
            context_note = (
                f"\n\nCurrent tiles on the grid: {current_summary}. "
                "Do not suggest tiles that duplicate existing ones unless the user asks."
            )

            messages = [
                {"role": m.role, "content": m.content}
                for m in body.messages
            ]
            if messages:
                messages[-1]["content"] = messages[-1]["content"] + context_note

            llm = create_llm(tier="small")
            response = llm.converse(
                system=system,
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
                tool_config=_TOOL_CONFIG,
                agent_task="audit_draft_assistant",
            )

            if response.text:
                yield _sse("text-delta", {"delta": response.text})

            for tool_use in response.tool_uses or []:
                tool_input = tool_use.get("input") or {}
                yield _sse(
                    "tool-input-available",
                    {
                        "toolName": tool_use.get("name", "design_report"),
                        "input": tool_input,
                    },
                )

            yield _sse("finish", {})

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
