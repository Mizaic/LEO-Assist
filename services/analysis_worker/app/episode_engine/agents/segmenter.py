"""Stage 2 agent: segment timeline into candidate episode windows."""

from __future__ import annotations

import logging

from libs.llm_client.factory import LLMClient
from libs.prompts.episode_engine import segmenter_v1
from services.analysis_worker.app.episode_engine.agents._common import call_stage
from services.analysis_worker.app.episode_engine.schemas import (
    SegmenterResult,
    StageTrace,
)

logger = logging.getLogger(__name__)


def run(
    *,
    llm: LLMClient,
    patient_id: str,
    timeline_text: str,
    max_tokens: int = 4096,
) -> tuple[SegmenterResult, StageTrace]:
    user = segmenter_v1.USER_TEMPLATE.format(
        patient_id=patient_id,
        timeline_text=timeline_text,
    )
    return call_stage(
        stage="segmenter",
        llm=llm,
        system=segmenter_v1.SYSTEM,
        user=user,
        schema=segmenter_v1.SCHEMA,
        tool_name=segmenter_v1.TOOL_NAME,
        response_model=SegmenterResult,
        prompt_version=segmenter_v1.VERSION,
        max_tokens=max_tokens,
    )
