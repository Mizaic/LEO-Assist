"""SBAR runtime helpers driven by pinned execution manifest (M2.3/M2.4).

Atlas trace:
  DO: DO-04CEDFB1
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-8788B246, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-04CEDFB1")
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from libs.llm_client.factory import create_llm
from libs.llm_client.json_helper import _extract_json
from libs.prompts.registry import get_prompt
from libs.sbar.prompt_calls import PromptFetcher
from libs.workflow.execution_manifest import manifest_from_json

logger = logging.getLogger(__name__)

StageName = str
LlmInvoker = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class SbarPolicyRuntime:
    execution_manifest: dict[str, Any]
    model_key: str = ""
    model_id: str = ""
    model_provider: str = ""
    model_tier: str = ""


def runtime_from_state(state: dict[str, Any]) -> SbarPolicyRuntime | None:
    raw = state.get("execution_manifest")
    if isinstance(raw, dict) and raw:
        return build_runtime(raw)
    raw_json = state.get("execution_manifest_json")
    if isinstance(raw_json, str) and raw_json.strip():
        return build_runtime(manifest_from_json(raw_json))
    return None


def build_runtime(manifest: dict[str, Any]) -> SbarPolicyRuntime:
    model = manifest.get("model") or {}
    return SbarPolicyRuntime(
        execution_manifest=manifest,
        model_key=str(model.get("key") or ""),
        model_id=str(model.get("modelId") or ""),
        model_provider=str(model.get("provider") or "azure"),
        model_tier=str(model.get("tier") or "big"),
    )


def make_prompt_fetcher(runtime: SbarPolicyRuntime) -> PromptFetcher:
    prompts = runtime.execution_manifest.get("prompts") or {}

    def _fetch(stage: str) -> str:
        pin = prompts.get(stage) or {}
        name = str(pin.get("name") or "")
        version = int(pin.get("version") or 1)
        if not name:
            raise RuntimeError(f"execution manifest missing prompt pin for {stage!r}")
        return get_prompt(name, version=version)

    def fetcher(prompt_name: str) -> str:
        stage_map = {
            "sbar_situation": "situation",
            "sbar_background": "background",
            "sbar_recommendation": "recommendation",
            "sbar_recall": "recall",
        }
        stage = stage_map.get(prompt_name, prompt_name)
        return _fetch(stage)

    return fetcher


def stage_llm_params(runtime: SbarPolicyRuntime, stage: StageName) -> dict[str, Any]:
    llm = runtime.execution_manifest.get("llm") or {}
    stage_cfg = llm.get(stage) or {}
    default_tokens = 512 if stage == "recall" else 1024
    return {
        "max_tokens": int(stage_cfg.get("maxTokens") or default_tokens),
        "temperature": float(stage_cfg.get("temperature") or 0.0),
    }


def make_llm_invoker(runtime: SbarPolicyRuntime, stage: StageName) -> LlmInvoker:
    params = stage_llm_params(runtime, stage)
    provider = runtime.model_provider or "azure"
    tier = runtime.model_tier or "big"

    async def _invoke(
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        agent_task: str = "unknown",
        patient_id: str = "",
        **_ignored: Any,
    ) -> dict[str, Any]:
        client = await asyncio.to_thread(create_llm, provider=provider, tier=tier)
        resp = await asyncio.to_thread(
            client.converse,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=max_tokens if max_tokens is not None else params["max_tokens"],
            temperature=(
                temperature if temperature is not None else params["temperature"]
            ),
            agent_task=agent_task,
            patient_id=patient_id,
        )
        raw_text = (resp.text or "").strip()
        try:
            parsed = _extract_json(raw_text)
        except Exception as exc:
            return {"error": f"json_parse_failed:{exc}", "raw_text": raw_text[:400]}
        parsed["_model_config"] = {
            "key": runtime.model_key or f"{provider}:{tier}",
            "provider": provider,
            "tier": tier,
            "model_id": runtime.model_id or getattr(resp, "model_id", ""),
        }
        parsed["_prompt_stage"] = stage
        return parsed

    return _invoke


def provenance_from_invocation(raw: dict[str, Any]) -> dict[str, Any]:
    model_cfg = raw.get("_model_config") or {}
    return {
        "model_config_key": str(model_cfg.get("key") or ""),
        "model_id": str(model_cfg.get("model_id") or ""),
        "model_provider": str(model_cfg.get("provider") or ""),
        "model_tier": str(model_cfg.get("tier") or ""),
        "prompt_stage": str(raw.get("_prompt_stage") or ""),
    }


def load_execution_manifest(client: Any, run_id: str) -> dict[str, Any]:
    from libs.cypher.pipeline_stage_queries import GET_PIPELINE_RUN_EXECUTION_MANIFEST

    rows = client.run(GET_PIPELINE_RUN_EXECUTION_MANIFEST, run_id=run_id)
    if not rows:
        return {}
    return manifest_from_json(str(rows[0].get("execution_manifest_json") or ""))
