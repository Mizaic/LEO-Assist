"""LLM provider management with Bedrock primary and Azure OpenAI fallback.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Ported from auditor_2 agent/core/models.py.
Decoupled from agent-specific tool bindings.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from functools import lru_cache
from typing import Any, List, Optional, Sequence

logger = logging.getLogger("libs.llm_client.providers")

_BEDROCK_MODEL = None
_USE_AZURE_PRIMARY = os.getenv("USE_AZURE_PRIMARY", "false").lower() in (
    "true",
    "1",
    "yes",
)


def _bedrock_model_id() -> str:
    model_id = (
        os.getenv("AWS_BEDROCK_MODEL", "").strip()
        or os.getenv("AWS_BIG_MODEL", "").strip()
    )
    if not model_id:
        raise RuntimeError(
            "AWS_BEDROCK_MODEL or AWS_BIG_MODEL must be set (Bedrock model ARN or ID)"
        )
    return model_id


async def get_bedrock_model():
    """Lazily create or return a cached ChatBedrockConverse instance."""
    global _BEDROCK_MODEL
    if _BEDROCK_MODEL:
        return _BEDROCK_MODEL

    from langchain_aws import ChatBedrockConverse

    from libs.llm_client.bedrock_client import get_bedrock_runtime_client

    region = os.getenv("AWS_DEFAULT_REGION", "eu-west-2")
    client = await asyncio.to_thread(
        get_bedrock_runtime_client,
        region,
        60,
        300,
        3,
        False,
    )
    _BEDROCK_MODEL = ChatBedrockConverse(
        model=_bedrock_model_id(),
        region_name=region,
        provider="anthropic",
        client=client,
    )
    return _BEDROCK_MODEL


def get_azure_model():
    """Return a process-wide cached AzureChatOpenAI instance.

    The underlying httpx client / connection pool is expensive to spin
    up on each call, so we memoise the wrapper keyed on the configured
    endpoint, deployment, and api version. Any change to env vars
    (test reload, key rotation) invalidates the cache automatically.
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_BIG_MODEL", "gpt-4o")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI credentials not configured")

    return _cached_azure_model(
        endpoint=endpoint,
        api_key=api_key,
        deployment=deployment,
        api_version=api_version,
    )


@lru_cache(maxsize=8)
def _cached_azure_model(
    *, endpoint: str, api_key: str, deployment: str, api_version: str
):
    from langchain_openai import AzureChatOpenAI
    from pydantic import SecretStr

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=SecretStr(api_key),
        azure_deployment=deployment,
        api_version=api_version,
    )


def reset_azure_model_cache() -> None:
    """Clear cached AzureChatOpenAI wrappers (test hook)."""
    _cached_azure_model.cache_clear()


def reset_bedrock_model_cache() -> None:
    """Clear cached ChatBedrockConverse wrapper (test hook)."""
    global _BEDROCK_MODEL
    from libs.llm_client.bedrock_client import reset_bedrock_client_cache

    _BEDROCK_MODEL = None
    reset_bedrock_client_cache()


async def invoke_with_retry(
    model, messages, config=None, *, max_retries: int = 5
) -> Any:
    """Invoke a model with exponential-backoff retry on transient errors."""
    from urllib3.exceptions import ConnectTimeoutError, ReadTimeoutError

    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return await model.ainvoke(messages, config)
        except (ReadTimeoutError, ConnectTimeoutError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = min(2**attempt, 30) + random.uniform(0, 1)
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as exc:
            last_exc = exc
            err = str(exc).lower()
            if any(kw in err for kw in ("throttling", "too many tokens", "rate")):
                if attempt < max_retries - 1:
                    delay = min(2 * 2**attempt, 60) + random.uniform(0, 2)
                    await asyncio.sleep(delay)
                else:
                    raise
            else:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("All retries exhausted")


async def invoke_with_fallback(
    model,
    messages,
    config=None,
    *,
    max_retries: int = 5,
    tools: Optional[Sequence] = None,
    agent_task: str = "unknown",
    patient_id: str = "",
) -> Any:
    """Try Bedrock first; on failure fall back to Azure OpenAI.

    If ``USE_AZURE_PRIMARY`` is set, Azure is used directly.
    ``tools`` is an optional sequence of LangChain tool definitions;
    if provided the model will be bound to them before invocation.

    DI-LEO-AI-515: every successful response fires a single
    :func:`libs.llm_client.token_tracker.track_llm_usage` event tagged
    with the provider that actually answered (``"bedrock"`` or
    ``"azure"``), so cost telemetry flows through the active
    ``LLMUsageRecorder`` and into the dashboard / per-tenant billing
    surfaces. Failures fire one tracking event per attempted provider
    with ``success=False`` and zero token counts.
    """
    azure_model_name = f"azure-{os.getenv('AZURE_OPENAI_BIG_MODEL', 'gpt-4o')}"
    bedrock_model_name = _bedrock_model_id().split("/")[-1] or "bedrock"

    if _USE_AZURE_PRIMARY:
        azure = get_azure_model()
        m = azure.bind_tools(tools) if tools else azure
        started = time.monotonic()
        try:
            response = await m.ainvoke(messages, config)
        except Exception as exc:
            await _fire_invoke_tracking(
                response=None,
                provider="azure",
                model_name=azure_model_name,
                agent_task=agent_task,
                patient_id=patient_id,
                started=started,
                success=False,
                error_message=str(exc),
            )
            raise
        await _fire_invoke_tracking(
            response=response,
            provider="azure",
            model_name=azure_model_name,
            agent_task=agent_task,
            patient_id=patient_id,
            started=started,
            success=True,
        )
        return response

    bedrock_started = time.monotonic()
    try:
        bound = model.bind_tools(tools) if tools else model
        response = await invoke_with_retry(
            bound, messages, config, max_retries=max_retries
        )
    except Exception as bedrock_err:
        await _fire_invoke_tracking(
            response=None,
            provider="bedrock",
            model_name=bedrock_model_name,
            agent_task=agent_task,
            patient_id=patient_id,
            started=bedrock_started,
            success=False,
            error_message=str(bedrock_err),
        )
        logger.warning("Bedrock failed, falling back to Azure: %s", bedrock_err)
        azure_started = time.monotonic()
        try:
            azure = get_azure_model()
            m = azure.bind_tools(tools) if tools else azure
            response = await m.ainvoke(messages, config)
        except Exception as azure_err:
            await _fire_invoke_tracking(
                response=None,
                provider="azure",
                model_name=azure_model_name,
                agent_task=agent_task,
                patient_id=patient_id,
                started=azure_started,
                success=False,
                error_message=str(azure_err),
            )
            logger.error(
                "Both Bedrock and Azure failed: %s / %s", bedrock_err, azure_err
            )
            raise
        await _fire_invoke_tracking(
            response=response,
            provider="azure",
            model_name=azure_model_name,
            agent_task=agent_task,
            patient_id=patient_id,
            started=azure_started,
            success=True,
        )
        return response

    await _fire_invoke_tracking(
        response=response,
        provider="bedrock",
        model_name=bedrock_model_name,
        agent_task=agent_task,
        patient_id=patient_id,
        started=bedrock_started,
        success=True,
    )
    return response


async def _fire_invoke_tracking(
    *,
    response: Any,
    provider: str,
    model_name: str,
    agent_task: str,
    patient_id: str,
    started: float,
    success: bool,
    error_message: str = "",
) -> None:
    """Best-effort wrapper around :func:`track_llm_usage` for invoke_with_fallback.

    Pulls token counts from the langchain response via
    :func:`extract_token_counts` (returns zeros when usage is missing
    or extraction raises) and forwards them to the registered tracking
    callback. Any failure inside this helper is swallowed so the
    caller is never broken.
    """
    from libs.llm_client.token_tracker import (
        extract_token_counts,
        track_llm_usage,
    )

    latency_ms = int((time.monotonic() - started) * 1000)
    counts: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_token_details": None,
        "output_token_details": None,
    }
    if response is not None:
        try:
            counts = extract_token_counts(response, provider)
        except Exception:
            logger.debug("extract_token_counts failed", exc_info=True)
    try:
        await track_llm_usage(
            model_name=model_name,
            model_provider=provider,
            agent_task=agent_task,
            patient_id=patient_id,
            latency_ms=latency_ms,
            success=success,
            error_message=str(error_message or "")[:400],
            input_excludes_cache=provider in ("aws", "bedrock"),
            **counts,
        )
    except Exception:
        logger.debug("invoke_with_fallback telemetry emission failed", exc_info=True)
