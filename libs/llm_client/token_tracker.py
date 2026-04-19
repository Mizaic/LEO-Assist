"""Token usage extraction and tracking utilities.

Provides provider-agnostic token counting from LLM responses and
an async tracking hook that services can use to record usage.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("libs.llm_client.token_tracker")

_tracking_callback: Optional[Callable[..., Any]] = None


def set_tracking_callback(callback: Callable[..., Any]) -> None:
    """Register a callback that will be invoked for every LLM call.

    The callback receives keyword arguments:
        model_name, model_provider, agent_task, input_tokens, output_tokens,
        latency_ms, patient_id, organization_id, success, error_message,
        cache_creation_input_tokens, cache_read_input_tokens,
        input_token_details, output_token_details
    """
    global _tracking_callback
    _tracking_callback = callback


def extract_token_counts(response: Any, provider: str) -> Dict[str, Any]:
    """Extract token counts from a Bedrock or Azure response object."""
    counts: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_token_details": None,
        "output_token_details": None,
    }
    usage = getattr(response, "usage_metadata", None) or {}
    if isinstance(usage, dict):
        counts["input_tokens"] = usage.get("input_tokens", 0)
        counts["output_tokens"] = usage.get("output_tokens", 0)
    else:
        counts["input_tokens"] = getattr(usage, "input_tokens", 0)
        counts["output_tokens"] = getattr(usage, "output_tokens", 0)

    meta = getattr(response, "response_metadata", {})
    if provider == "bedrock":
        bu = meta.get("usage", {})
        counts["cache_creation_input_tokens"] = bu.get("cache_creation_input_tokens", 0)
        counts["cache_read_input_tokens"] = bu.get("cache_read_input_tokens", 0)
    elif provider == "azure":
        prompt_details = meta.get("token_usage", {}).get("prompt_tokens_details")
        completion_details = meta.get("token_usage", {}).get(
            "completion_tokens_details"
        )
        counts["input_token_details"] = prompt_details
        counts["output_token_details"] = completion_details
    return counts


async def track_llm_usage(**kwargs: Any) -> None:
    """Fire-and-forget: call the registered tracking callback if one exists."""
    if _tracking_callback:
        try:
            result = _tracking_callback(**kwargs)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.debug("Token tracking callback failed", exc_info=True)


def track_llm_usage_sync(**kwargs: Any) -> None:
    """Sync variant of :func:`track_llm_usage` for sync LLM entry points.

    Used by ``libs.llm_client.factory.LLMClient.converse`` and other
    synchronous callers that cannot await ``track_llm_usage``. Behaviour:

    - If no callback is registered, this is a no-op.
    - If the callback returns ``None`` (the common case -- the default
      ``LLMUsageRecorder`` callback is sync), nothing else happens.
    - If the callback returns a coroutine, we try to schedule it on the
      currently running asyncio loop. If no loop is running in this
      thread (typical when ``LLMClient.converse`` is called inside
      ``asyncio.to_thread``), we drain the coroutine via
      ``asyncio.run`` so the work still happens.
    - Any exception from the callback path is swallowed and logged at
      DEBUG, so a tracking-callback bug never breaks the LLM caller.
    """
    if _tracking_callback is None:
        return
    try:
        result = _tracking_callback(**kwargs)
    except Exception:
        logger.debug("Token tracking callback failed (sync)", exc_info=True)
        return
    if not hasattr(result, "__await__"):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(result)
        except Exception:
            logger.debug(
                "Token tracking callback (sync, async drain) failed",
                exc_info=True,
            )
        return
    try:
        loop.create_task(result)
    except Exception:
        logger.debug(
            "Token tracking callback (sync, schedule on loop) failed",
            exc_info=True,
        )


def get_model_name_from_arn(arn: str) -> str:
    if not arn:
        return "unknown-bedrock"
    parts = arn.split("/")
    return parts[-1] if parts else arn


def get_azure_model_name(deployment: str) -> str:
    return f"azure-{deployment}"
