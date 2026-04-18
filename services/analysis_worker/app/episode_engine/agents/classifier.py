"""Stage 3 agent: classify a single candidate window."""

from __future__ import annotations

from libs.llm_client.factory import LLMClient
from libs.prompts.episode_engine import classifier_v1
from services.analysis_worker.app.episode_engine.agents._common import call_stage
from services.analysis_worker.app.episode_engine.schemas import (
    ClassifierResult,
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
    window_text: str,
    max_tokens: int = 1024,
) -> tuple[ClassifierResult, StageTrace]:
    user = classifier_v1.USER_TEMPLATE.format(
        patient_id=patient_id,
        window_id=window_id,
        suspected_site=suspected_site,
        window_start=window_start,
        window_end=window_end or "open",
        window_text=window_text,
    )
    return call_stage(
        stage="classifier",
        llm=llm,
        system=classifier_v1.SYSTEM,
        user=user,
        schema=classifier_v1.SCHEMA,
        tool_name=classifier_v1.TOOL_NAME,
        response_model=ClassifierResult,
        prompt_version=classifier_v1.VERSION,
        max_tokens=max_tokens,
    )
