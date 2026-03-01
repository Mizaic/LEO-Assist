"""Agent endpoints: interpret measures, executive summary.

Report builder AI features. Stub implementation until LLM integration is added.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_access_token

router = APIRouter(prefix="/agent", tags=["agent"])


class InterpretMeasuresRequest(BaseModel):
    report_id: str
    measure_ids: Optional[List[str]] = None
    measure_id: Optional[str] = None
    measure_reports: Optional[List[Dict[str, Any]]] = None
    measure_title_overrides: Optional[Dict[str, str]] = None
    model_size: Optional[str] = "small"
    user_goal: Optional[str] = None
    organization_id: Optional[str] = None
    cohort_filters: Optional[Dict[str, Any]] = None


class InterpretMeasuresResponse(BaseModel):
    reportId: str
    interpretation: Dict[str, Any]


class ExecutiveSummaryRequest(BaseModel):
    report_id: str
    summaries: Optional[List[Dict[str, Any]]] = None
    excluded_measure_ids: Optional[List[str]] = None
    mode: Optional[str] = "default"
    model_size: Optional[str] = "small"


class ExecutiveSummaryResponse(BaseModel):
    reportId: str
    summary: str
    mode: str
    generated_at: str


@router.post("/interpret", response_model=InterpretMeasuresResponse)
async def interpret_measures(
    body: InterpretMeasuresRequest,
    _token: str = Depends(get_access_token),
):
    """Interpret measure data with AI. Stub: returns placeholder until LLM integration."""
    # Stub response - replace with real LLM call when integration is ready
    return InterpretMeasuresResponse(
        reportId=body.report_id,
        interpretation={
            "summary": "AI interpretation is not yet configured. Connect an LLM provider (e.g. OpenAI, Bedrock) to enable this feature.",
            "insights": [],
            "quality_checks": [],
            "recommended_measures": [],
            "follow_up_questions": [],
            "caveats": ["Interpretation service is a stub. No analysis was performed."],
            "model": {"size": body.model_size or "small", "id": "stub"},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.post("/executive-summary", response_model=ExecutiveSummaryResponse)
async def executive_summary(
    body: ExecutiveSummaryRequest,
    _token: str = Depends(get_access_token),
):
    """Generate executive summary from interpretation summaries. Stub until LLM integration."""
    return ExecutiveSummaryResponse(
        reportId=body.report_id,
        summary="Executive summary is not yet configured. Connect an LLM provider to enable this feature.",
        mode=body.mode or "default",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
