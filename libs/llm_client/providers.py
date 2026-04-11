"""LLM provider management with Bedrock primary and Azure OpenAI fallback.

Ported from auditor_2 agent/core/models.py.
Decoupled from agent-specific tool bindings.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, List, Optional, Sequence

logger = logging.getLogger("libs.llm_client.providers")

_BEDROCK_MODEL = None
_USE_AZURE_PRIMARY = os.getenv("USE_AZURE_PRIMARY", "false").lower() in (
    "true",
    "1",
    "yes",
)


def _bedrock_model_id() -> str:
    return os.getenv(
        "AWS_BEDROCK_MODEL",
        "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


async def get_bedrock_model():
    """Lazily create or return a cached ChatBedrockConverse instance."""
    global _BEDROCK_MODEL
    if _BEDROCK_MODEL:
        return _BEDROCK_MODEL

    import boto3
    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse

    cfg = Config(
        connect_timeout=60,
        read_timeout=300,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    client = await asyncio.to_thread(
        lambda: boto3.client(
            "bedrock-runtime", region_name="eu-west-2", config=cfg, verify=True
        )
    )
    _BEDROCK_MODEL = ChatBedrockConverse(
        model=_bedrock_model_id(),
        region_name="eu-west-2",
        provider="anthropic",
        client=client,
    )
    return _BEDROCK_MODEL


def get_azure_model():
    """Create an AzureChatOpenAI instance from environment variables."""
    from langchain_openai import AzureChatOpenAI
    from pydantic import SecretStr

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_BIG_MODEL", "gpt-4o")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI credentials not configured")

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=SecretStr(api_key),
        azure_deployment=deployment,
        api_version=api_version,
    )


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
) -> Any:
    """Try Bedrock first; on failure fall back to Azure OpenAI.

    If ``USE_AZURE_PRIMARY`` is set, Azure is used directly.
    ``tools`` is an optional sequence of LangChain tool definitions;
    if provided the model will be bound to them before invocation.
    """
    if _USE_AZURE_PRIMARY:
        azure = get_azure_model()
        m = azure.bind_tools(tools) if tools else azure
        return await m.ainvoke(messages, config)

    try:
        bound = model.bind_tools(tools) if tools else model
        return await invoke_with_retry(bound, messages, config, max_retries=max_retries)
    except Exception as bedrock_err:
        logger.warning("Bedrock failed, falling back to Azure: %s", bedrock_err)
        try:
            azure = get_azure_model()
            m = azure.bind_tools(tools) if tools else azure
            return await m.ainvoke(messages, config)
        except Exception as azure_err:
            logger.error(
                "Both Bedrock and Azure failed: %s / %s", bedrock_err, azure_err
            )
            raise
