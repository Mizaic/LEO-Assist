"""Validation Lab guided brainstorm API.

Atlas trace:
  DO: DO-A0ADDB38
  DI: DI-EB716E68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.validation_lab.brainstorm import (
    run_propose_variants,
    run_understand_or_clarify,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/validation-lab", tags=["validation-lab-brainstorm"])


class RecommendationAttach(BaseModel):
    recId: str = ""
    guidelineCode: str = ""
    verbatim: str = ""
    recTitle: str = ""
    ruleId: str = ""
    ruleStatus: str = ""


class BrainstormBody(BaseModel):
    phase: Literal["understand", "clarify", "propose_variants"]
    scenario_text: str = ""
    recommendations: list[RecommendationAttach] = Field(default_factory=list)
    answers: dict[str, Any] = Field(default_factory=dict)
    round: int = 0
    include_control: bool = False


def _recs_as_dicts(body: BrainstormBody) -> list[dict[str, Any]]:
    return [r.model_dump() for r in body.recommendations]


@router.post("/brainstorm")
def brainstorm(
    body: BrainstormBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Guided understand / clarify / propose_variants brainstorm turn."""
    try:
        if body.phase in ("understand", "clarify"):
            result = run_understand_or_clarify(
                phase=body.phase,
                scenario_text=body.scenario_text,
                recommendations=_recs_as_dicts(body),
                answers=body.answers,
                round=body.round,
            )
            result.setdefault("variants", [])
            return result
        result = run_propose_variants(
            scenario_text=body.scenario_text,
            recommendations=_recs_as_dicts(body),
            answers=body.answers,
            include_control=body.include_control,
        )
        result.setdefault("needs_clarification", False)
        result.setdefault("questions", [])
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("validation_lab.brainstorm failed")
        raise HTTPException(status_code=500, detail="Unable to run brainstorm") from exc
