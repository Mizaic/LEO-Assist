"""Unified sync LLM provider factory.

Returns a lightweight ``LLMClient`` with a ``.converse()`` method that works
identically regardless of whether the backend is AWS Bedrock or Azure OpenAI.

Design decisions (see plan M2c):
- Sync interface: matches the V3 pipeline's sync architecture.
- The coding worker (async) wraps calls with ``asyncio.to_thread()``.
- No LangChain dependency — raw ``boto3`` and ``openai`` for minimal overhead.

Usage::

    from libs.llm_client.factory import create_llm

    client = create_llm(provider="aws", tier="small")
    response = client.converse(
        system="You are a clinical coder.",
        messages=[{"role": "user", "content": "Extract entities from: ..."}],
    )
    print(response.text)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_TIER_ENV = {
    "aws": {
        "small": "AWS_SMALL_MODEL",
        "big": "AWS_BIG_MODEL",
        "max": "AWS_MAX_MODEL",
    },
    "azure": {
        "small": "AZURE_OPENAI_SMALL_MODEL",
        "big": "AZURE_OPENAI_BIG_MODEL",
        "max": "AZURE_OPENAI_BIG_MODEL",
    },
}

_AWS_DEFAULTS = {
    "small": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "big": "eu.anthropic.claude-sonnet-4-6",
    "max": "eu.anthropic.claude-opus-4-6-v1",
}

_AZURE_DEFAULTS = {
    "small": "gpt-5-mini",
    "big": "gpt-5",
    "max": "gpt-5",
}


@dataclass(frozen=True)
class LLMResponse:
    """Unified response from any provider."""
    text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    stop_reason: str
    model_id: str


class LLMClient:
    """Sync LLM client wrapping a single provider + model."""

    def __init__(self, provider: str, model_id: str, region: str | None = None):
        self.provider = provider
        self.model_id = model_id
        self.region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self.provider == "aws":
            self._client = self._init_bedrock()
        elif self.provider == "azure":
            self._client = self._init_azure()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
        return self._client

    def _init_bedrock(self) -> Any:
        import boto3
        from botocore.config import Config
        cfg = Config(
            connect_timeout=60,
            read_timeout=300,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        return boto3.client(
            "bedrock-runtime",
            region_name=self.region or os.getenv("AWS_DEFAULT_REGION", "eu-west-2"),
            config=cfg,
        )

    def _init_azure(self) -> Any:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        )

    def converse(
        self,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Synchronous call. Returns unified response regardless of provider."""
        client = self._get_client()
        if self.provider == "aws":
            return self._converse_bedrock(client, system, messages, max_tokens, temperature)
        else:
            return self._converse_azure(client, system, messages, max_tokens, temperature)

    def _converse_bedrock(
        self, client: Any, system: str, messages: list[dict], max_tokens: int, temperature: float,
    ) -> LLMResponse:
        from libs.llm_client.bedrock_retry import converse_with_retry

        bedrock_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                content = [{"text": content}]
            bedrock_messages.append({"role": role, "content": content})

        response = converse_with_retry(
            client,
            model_id=self.model_id,
            system=[{"text": system}],
            messages=bedrock_messages,
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )

        output_content = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [
            item["text"] for item in output_content
            if isinstance(item, dict) and "text" in item
        ]
        usage = response.get("usage", {})
        return LLMResponse(
            text="\n".join(text_parts).strip(),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            cached_input_tokens=usage.get("cacheReadInputTokenCount", 0),
            stop_reason=response.get("stopReason", ""),
            model_id=self.model_id,
        )

    def _converse_azure(
        self, client: Any, system: str, messages: list[dict], max_tokens: int, temperature: float,
    ) -> LLMResponse:
        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            oai_messages.append({"role": role, "content": content})

        response = client.chat.completions.create(
            model=self.model_id,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0] if response.choices else None
        usage = response.usage
        return LLMResponse(
            text=choice.message.content.strip() if choice and choice.message.content else "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=getattr(usage, "prompt_tokens_details", {}).get("cached_tokens", 0) if usage else 0,
            stop_reason=choice.finish_reason if choice else "",
            model_id=self.model_id,
        )


def create_llm(
    provider: str | None = None,
    tier: str = "small",
    *,
    model_id: str | None = None,
    region: str | None = None,
) -> LLMClient:
    """Create an LLM client for the given provider and tier.

    Args:
        provider: ``"aws"`` or ``"azure"``. Defaults to ``PIPELINE_MODEL_PROVIDER`` env var.
        tier: ``"small"``, ``"big"``, or ``"max"``.
        model_id: Explicit model ID (overrides tier lookup).
        region: AWS region (only for Bedrock).
    """
    if provider is None:
        provider = os.getenv("PIPELINE_MODEL_PROVIDER", "aws")

    if model_id is None:
        env_key = _TIER_ENV.get(provider, {}).get(tier)
        if env_key:
            defaults = _AWS_DEFAULTS if provider == "aws" else _AZURE_DEFAULTS
            model_id = os.getenv(env_key, defaults.get(tier, ""))
        if not model_id:
            raise ValueError(f"No model configured for provider={provider}, tier={tier}")

    return LLMClient(provider=provider, model_id=model_id, region=region)
