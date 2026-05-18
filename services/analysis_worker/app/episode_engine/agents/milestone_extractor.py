"""Stage 4 agent: extract milestones from a cancer/multi-site window.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")
"""

from __future__ import annotations

from libs.llm_client.factory import LLMClient
from libs.prompts.episode_engine import milestone_extractor_v1
from services.analysis_worker.app.episode_engine.agents._common import call_stage
from services.analysis_worker.app.episode_engine.schemas import (
    MilestoneExtractorResult,
    StageTrace,
)


def run(
    *,
    llm: LLMClient,
    patient_id: str,
    window_id: str,
    suspected_site: str,
    window_start: str,
    window_end: str,
    window_full_text: str,
    max_tokens: int = 4096,
) -> tuple[MilestoneExtractorResult, StageTrace]:
    user = milestone_extractor_v1.USER_TEMPLATE.format(
        patient_id=patient_id,
        window_id=window_id,
        suspected_site=suspected_site,
        window_start=window_start,
        window_end=window_end or "open",
        window_full_text=window_full_text,
    )
    return call_stage(
        stage="milestone_extractor",
        llm=llm,
        system=milestone_extractor_v1.SYSTEM,
        user=user,
        schema=milestone_extractor_v1.SCHEMA,
        tool_name=milestone_extractor_v1.TOOL_NAME,
        response_model=MilestoneExtractorResult,
        prompt_version=milestone_extractor_v1.VERSION,
        max_tokens=max_tokens,
    )
