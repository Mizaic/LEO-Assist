"""Shared helpers for episode-engine agents.

Wraps the common boilerplate of:
  - building Bedrock toolConfig from a JSON Schema
  - calling LLMClient.converse(...)
  - extracting the toolUse JSON
  - validating via a Pydantic model
  - capturing a StageTrace for provenance
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from libs.llm_client.factory import LLMClient
from libs.llm_usage import LLMCostConfig, LLMUsage
from services.analysis_worker.app.episode_engine.schemas import StageTrace

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StageError(RuntimeError):
    """Raised when an agent stage cannot produce a valid response."""


def build_tool_config(tool_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap a JSON Schema in the Bedrock toolConfig structure that Claude
    needs to be FORCED to call the tool (and so emit valid JSON)."""

    return {
        "tools": [
            {
                "toolSpec": {
                    "name": tool_name,
                    "description": (
                        "Submit the structured episode-engine response. "
                        "Always call this tool exactly once."
                    ),
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": tool_name}},
    }


def _extract_tool_input(
    tool_uses: list[dict[str, Any]], tool_name: str
) -> dict[str, Any] | None:
    for tu in tool_uses:
        if not isinstance(tu, dict):
            continue
        if tu.get("name") != tool_name:
            continue
        payload = tu.get("input") or {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return None


def call_stage(
    *,
    stage: str,
    llm: LLMClient,
    system: str,
    user: str,
    schema: dict[str, Any],
    tool_name: str,
    response_model: type[T],
    prompt_version: str,
    max_tokens: int = 4096,
) -> tuple[T, StageTrace]:
    """Run one stage end-to-end and return ``(parsed_response, trace)``.

    Raises ``StageError`` on irrecoverable failure (the chain decides
    whether to fail-fast or fail-soft per stage).
    """

    tier = getattr(llm, "tier", "") or ""
    started = time.perf_counter()
    trace = StageTrace(
        stage=stage,
        prompt_version=prompt_version,
        model_id=llm.model_id,
        tier=tier,
    )
    try:
        resp = llm.converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            tool_config=build_tool_config(tool_name, schema),
            max_tokens=max_tokens,
        )
    except Exception as exc:
        trace.ok = False
        trace.error = f"{type(exc).__name__}: {exc}"
        trace.latency_ms = int((time.perf_counter() - started) * 1000)
        raise StageError(f"{stage}: LLM call failed: {exc}") from exc

    trace.input_tokens = int(resp.input_tokens or 0)
    trace.output_tokens = int(resp.output_tokens or 0)
    trace.cached_input_tokens = int(getattr(resp, "cached_input_tokens", 0) or 0)
    trace.latency_ms = int((time.perf_counter() - started) * 1000)
    trace.model_id = resp.model_id or llm.model_id

    # Cost is best-effort: if the env vars for this tier are not set,
    # cost_usd is 0 and we still record token counts.
    try:
        usage = LLMUsage(
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            cached_input_tokens=trace.cached_input_tokens,
            llm_calls=1,
        )
        cfg = LLMCostConfig.for_tier(tier or "small")
        trace.cost_usd = round(usage.cost_usd(cfg), 6)
    except Exception:
        logger.debug(
            "Stage %s: cost calc failed; leaving cost_usd=0", stage, exc_info=True
        )
        trace.cost_usd = 0.0

    payload = _extract_tool_input(resp.tool_uses or [], tool_name)
    if payload is None:
        trace.ok = False
        trace.error = (
            f"no toolUse named {tool_name!r} in response "
            f"(stop_reason={resp.stop_reason!r}, text_len={len(resp.text)})"
        )
        raise StageError(trace.error)

    try:
        parsed = response_model.model_validate(payload)
    except ValidationError as exc:
        trace.ok = False
        trace.error = f"schema validation failed: {exc.error_count()} errors"
        logger.warning(
            "Stage %s schema validation failed for %s: %s\nPayload: %s",
            stage,
            response_model.__name__,
            exc,
            json.dumps(payload)[:1000],
        )
        raise StageError(trace.error) from exc

    return parsed, trace
