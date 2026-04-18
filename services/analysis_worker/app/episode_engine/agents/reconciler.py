"""Stage 5 agent: reconcile candidate windows + milestones into final episodes.

Defaults to Sonnet (``tier="big"``) because reconciliation needs to reason
across multiple windows. Spike data may show Haiku is sufficient; the chain
allows the tier to be overridden.
"""

from __future__ import annotations

import json
from typing import Any

from libs.llm_client.factory import LLMClient
from libs.prompts.episode_engine import reconciler_v1
from services.analysis_worker.app.episode_engine.agents._common import call_stage
from services.analysis_worker.app.episode_engine.schemas import (
    ReconcilerResult,
    StageTrace,
)


def run(
    *,
    llm: LLMClient,
    patient_id: str,
    candidates: list[dict[str, Any]],
    max_tokens: int = 6144,
) -> tuple[ReconcilerResult, StageTrace]:
    user = reconciler_v1.USER_TEMPLATE.format(
        patient_id=patient_id,
        candidate_payload=json.dumps(candidates, default=str, indent=2),
    )
    return call_stage(
        stage="reconciler",
        llm=llm,
        system=reconciler_v1.SYSTEM,
        user=user,
        schema=reconciler_v1.SCHEMA,
        tool_name=reconciler_v1.TOOL_NAME,
        response_model=ReconcilerResult,
        prompt_version=reconciler_v1.VERSION,
        max_tokens=max_tokens,
    )
