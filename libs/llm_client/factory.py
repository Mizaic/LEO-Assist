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
import random
import time
from dataclasses import dataclass, field
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
    tool_uses: list[dict[str, Any]] = field(default_factory=list)


# Thinking-token budgets per tier (AWS extended thinking).
# Small models get a lighter budget — Haiku doesn't need 8k thinking tokens for
# most audit verdicts, and it keeps per-record cost reasonable.
_REASONING_BUDGET_BY_TIER: dict[str, int] = {
    "small": int(os.getenv("AUDIT_REASONING_BUDGET_SMALL", "2000")),
    "big":   int(os.getenv("AUDIT_REASONING_BUDGET_BIG",   "8000")),
    "max":   int(os.getenv("AUDIT_REASONING_BUDGET_MAX",  "10000")),
}
_DEFAULT_REASONING_BUDGET = int(os.getenv("AUDIT_REASONING_BUDGET_TOKENS", "8000"))

# Azure reasoning_effort per tier.
# Small models use "low" — they're fast and we run two in parallel; the cost
# of heavy reasoning on every cheap-consensus record adds up quickly.
# Big/max use "high" — only called on escalated records, worth the extra thinking.
_AZURE_REASONING_EFFORT_BY_TIER: dict[str, str] = {
    "small": os.getenv("AZURE_REASONING_EFFORT_SMALL", "low"),
    "big":   os.getenv("AZURE_REASONING_EFFORT_BIG",   "high"),
    "max":   os.getenv("AZURE_REASONING_EFFORT_MAX",   "high"),
}
_AZURE_REASONING_EFFORT = os.getenv("AZURE_REASONING_EFFORT", "high")  # legacy override


class LLMClient:
    """Sync LLM client wrapping a single provider + model."""

    def __init__(
        self,
        provider: str,
        model_id: str,
        tier: str = "big",
        region: str | None = None,
        use_reasoning: bool = False,
        reasoning_budget: int = _DEFAULT_REASONING_BUDGET,
        azure_reasoning_effort: str = _AZURE_REASONING_EFFORT,
    ):
        self.provider = provider
        self.model_id = model_id
        self.tier = tier
        self.region = region
        self.use_reasoning = use_reasoning
        self.reasoning_budget = reasoning_budget
        self.azure_reasoning_effort = azure_reasoning_effort
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
        import httpx
        from openai import AzureOpenAI

        # Explicit timeout so the client fails fast with a clear error rather than
        # hanging until concurrent.futures kills the thread (which leaves a zombie).
        # Set lower than the consensus runner's fut_azure.result(timeout=60) so we
        # get a clean openai.APITimeoutError rather than a Future TimeoutError.
        connect_timeout = float(os.getenv("AZURE_OPENAI_CONNECT_TIMEOUT", "10.0"))
        read_timeout = float(os.getenv("AZURE_OPENAI_READ_TIMEOUT", "45.0"))

        return AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            # Disable the SDK's built-in retries — we handle them ourselves in
            # _converse_azure so we can log each attempt at the right severity.
            max_retries=0,
        )

    def converse(
        self,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.0,
        tool_config: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Synchronous call. Returns unified response regardless of provider.

        Args:
            tool_config: Optional Bedrock toolConfig dict. When provided, passes
                it to the Converse API and populates LLMResponse.tool_uses with
                any toolUse content blocks returned. Ignored for Azure provider.
        """
        client = self._get_client()
        if self.provider == "aws":
            return self._converse_bedrock(client, system, messages, max_tokens, temperature, tool_config)
        else:
            return self._converse_azure(client, system, messages, max_tokens, temperature)

    def _converse_bedrock(
        self,
        client: Any,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        tool_config: dict[str, Any] | None = None,
    ) -> LLMResponse:
        from botocore.exceptions import ParamValidationError
        from libs.llm_client.bedrock_retry import converse_with_retry

        bedrock_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                content = [{"text": content}]
            bedrock_messages.append({"role": role, "content": content})

        # Extended thinking: temperature must be 1.0 (Bedrock hard requirement).
        # maxTokens must cover both thinking budget AND the response — add them.
        effective_temp      = 1.0 if self.use_reasoning else temperature
        effective_max_tokens = max_tokens + self.reasoning_budget if self.use_reasoning else max_tokens

        converse_kwargs: dict[str, Any] = dict(
            model_id=self.model_id,
            # Mark the static system prompt prefix cacheable for Bedrock prompt caching.
            system=[{"text": system}, {"cachePoint": {"type": "default"}}],
            messages=bedrock_messages,
            inferenceConfig={"maxTokens": effective_max_tokens, "temperature": effective_temp},
        )

        if self.use_reasoning:
            converse_kwargs["additionalModelRequestFields"] = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": self.reasoning_budget,
                }
            }
            if tool_config is not None:
                # Extended thinking and tool_config cannot be combined on Bedrock.
                logger.warning(
                    "use_reasoning=True is incompatible with tool_config on Bedrock — "
                    "tools disabled for this call (%s)", self.model_id,
                )
        elif tool_config is not None:
            converse_kwargs["toolConfig"] = tool_config

        try:
            response = converse_with_retry(client, **converse_kwargs)
        except ParamValidationError as exc:
            if "cachePoint" not in str(exc):
                raise
            logger.warning(
                "Bedrock model %s rejected cachePoint in system prompt; retrying without prompt caching marker.",
                self.model_id,
            )
            converse_kwargs["system"] = [{"text": system}]
            response = converse_with_retry(client, **converse_kwargs)

        output_content = response.get("output", {}).get("message", {}).get("content", [])
        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        for item in output_content:
            if not isinstance(item, dict):
                continue
            if "text" in item:
                text_parts.append(item["text"])
            elif "toolUse" in item:
                tool_uses.append(item["toolUse"])
            # reasoningContent blocks (extended thinking) are intentionally omitted
            # from the returned text — they represent internal chain-of-thought and
            # are not part of the structured audit verdict JSON.

        usage = response.get("usage", {})
        stop_reason = response.get("stopReason", "")
        text = "\n".join(text_parts).strip()

        if not text and not tool_uses:
            logger.warning(
                "Bedrock %s returned empty text content "
                "(stop_reason=%r, output_tokens=%d, reasoning_blocks_skipped=%d) "
                "-- possible guardrail, max_tokens exhaustion, or transient API issue",
                self.model_id,
                stop_reason,
                usage.get("outputTokens", 0),
                sum(1 for item in output_content if isinstance(item, dict) and "reasoningContent" in item),
            )

        return LLMResponse(
            text=text,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            cached_input_tokens=usage.get("cacheReadInputTokenCount", 0),
            stop_reason=stop_reason,
            model_id=self.model_id,
            tool_uses=tool_uses,
        )

    def _converse_azure(
        self,
        client: Any,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        *,
        _max_retries: int = 3,
        _base_delay: float = 1.0,
        _max_delay: float = 30.0,
    ) -> LLMResponse:
        # GPT-5 / o-series reasoning models prefer "developer" over "system".
        # Both work (the API treats them identically), but "developer" is the
        # recommended role per the Azure Foundry reasoning docs.
        system_role = "developer" if self.use_reasoning else "system"
        oai_messages = [{"role": system_role, "content": system}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            oai_messages.append({"role": role, "content": content})

        kwargs: dict[str, Any] = {"model": self.model_id, "messages": oai_messages}

        if self.use_reasoning:
            # Pick tier-appropriate effort; individual override via azure_reasoning_effort.
            effort = _AZURE_REASONING_EFFORT_BY_TIER.get(self.tier, self.azure_reasoning_effort)
            kwargs["reasoning_effort"] = effort
            # max_completion_tokens must cover reasoning tokens + response tokens.
            # GPT-5/o-series reasoning can consume thousands of tokens internally;
            # if the budget runs out before the response, we get empty content.
            # Scale up: response budget × 4 floor-capped at 16 000 for big models.
            scale = 2 if self.tier == "small" else 4
            kwargs["max_completion_tokens"] = max(max_tokens * scale, 8000)
            # temperature, top_p etc. are not supported by reasoning models.
        else:
            kwargs["max_completion_tokens"] = max_tokens
            if temperature != 0.0:
                kwargs["temperature"] = temperature

        from openai import APIConnectionError, APIStatusError, APITimeoutError

        _RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

        # Redact key for logging — show last 4 chars only
        _endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "<not set>")
        _key_hint = (os.getenv("AZURE_OPENAI_API_KEY") or "")[-4:] or "<not set>"
        _api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        logger.debug(
            "Azure call START: model=%s endpoint=%s api_version=%s key=****%s "
            "max_completion_tokens=%s reasoning_effort=%s use_reasoning=%s",
            self.model_id, _endpoint, _api_version, _key_hint,
            kwargs.get("max_completion_tokens"), kwargs.get("reasoning_effort"), self.use_reasoning,
        )

        last_exc: Exception | None = None
        for attempt in range(1, _max_retries + 1):
            t0 = time.monotonic()
            try:
                response = client.chat.completions.create(**kwargs)
                elapsed = time.monotonic() - t0

                if attempt > 1:
                    logger.info(
                        "Azure %s: recovered on attempt %d/%d (%.1fs).",
                        self.model_id, attempt, _max_retries, elapsed,
                    )
                else:
                    logger.debug(
                        "Azure %s: OK in %.1fs (attempt %d/%d).",
                        self.model_id, elapsed, attempt, _max_retries,
                    )
                break

            except APITimeoutError as exc:
                elapsed = time.monotonic() - t0
                last_exc = exc
                if attempt == _max_retries:
                    logger.error(
                        "Azure %s: TIMEOUT after %.1fs on final attempt %d/%d. "
                        "endpoint=%s model=%s key=****%s — check Azure portal for "
                        "deployment health and regional capacity.",
                        self.model_id, elapsed, attempt, _max_retries,
                        _endpoint, self.model_id, _key_hint,
                    )
                    raise
                delay = min(_max_delay, _base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
                logger.warning(
                    "Azure %s: TIMEOUT after %.1fs on attempt %d/%d — retrying in %.1fs. "
                    "endpoint=%s key=****%s",
                    self.model_id, elapsed, attempt, _max_retries, delay,
                    _endpoint, _key_hint,
                )
                time.sleep(delay)
                continue

            except APIConnectionError as exc:
                elapsed = time.monotonic() - t0
                last_exc = exc
                if attempt == _max_retries:
                    logger.error(
                        "Azure %s: CONNECTION ERROR after %.1fs on final attempt %d/%d. "
                        "endpoint=%s key=****%s — is the endpoint reachable from this host? "
                        "Error: %s",
                        self.model_id, elapsed, attempt, _max_retries,
                        _endpoint, _key_hint, exc,
                    )
                    raise
                delay = min(_max_delay, _base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
                logger.warning(
                    "Azure %s: connection error after %.1fs on attempt %d/%d — retrying in %.1fs: %s",
                    self.model_id, elapsed, attempt, _max_retries, delay, exc,
                )
                time.sleep(delay)
                continue

            except APIStatusError as exc:
                elapsed = time.monotonic() - t0
                if exc.status_code in _RETRYABLE_STATUS and attempt < _max_retries:
                    last_exc = exc
                    delay = min(_max_delay, _base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
                    logger.warning(
                        "Azure %s: HTTP %d after %.1fs on attempt %d/%d — retrying in %.1fs. "
                        "response_id=%s body=%.200s",
                        self.model_id, exc.status_code, elapsed, attempt, _max_retries, delay,
                        getattr(exc, "request_id", "?"),
                        str(getattr(exc, "response", ""))[:200],
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    "Azure %s: HTTP %s after %.1fs (not retrying). "
                    "endpoint=%s model=%s key=****%s request_id=%s body=%.300s",
                    self.model_id, exc.status_code, elapsed,
                    _endpoint, self.model_id, _key_hint,
                    getattr(exc, "request_id", "?"),
                    str(getattr(exc, "response", ""))[:300],
                )
                raise

            except Exception as exc:
                elapsed = time.monotonic() - t0
                # Graceful fallback: if the API rejects reasoning_effort (shouldn't
                # happen for gpt-5 / gpt-5-mini, but guards against mis-config),
                # retry without it using a standard call (one-time only).
                if self.use_reasoning and kwargs.get("reasoning_effort") is not None and attempt == 1:
                    logger.warning(
                        "Azure model %s rejected reasoning params after %.1fs — "
                        "retrying without reasoning_effort: %s",
                        self.model_id, elapsed, exc,
                    )
                    kwargs.pop("reasoning_effort", None)
                    kwargs["max_completion_tokens"] = max_tokens
                    if temperature != 0.0:
                        kwargs["temperature"] = temperature
                    continue
                logger.error(
                    "Azure %s: unexpected error after %.1fs on attempt %d/%d: %s",
                    self.model_id, elapsed, attempt, _max_retries, exc, exc_info=True,
                )
                raise

        choice = response.choices[0] if response.choices else None
        usage = response.usage
        # Extract reasoning_tokens from completion_tokens_details if present
        reasoning_tokens = 0
        if usage:
            ctd = getattr(usage, "completion_tokens_details", None)
            if ctd:
                reasoning_tokens = getattr(ctd, "reasoning_tokens", 0) or 0
        if self.use_reasoning and reasoning_tokens:
            logger.debug(
                "Azure %s reasoning_tokens=%d response_tokens=%d",
                self.model_id, reasoning_tokens,
                (usage.completion_tokens - reasoning_tokens) if usage else 0,
            )
        return LLMResponse(
            text=choice.message.content.strip() if choice and choice.message.content else "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) if usage else 0,
            stop_reason=choice.finish_reason if choice else "",
            model_id=self.model_id,
        )


def create_llm(
    provider: str | None = None,
    tier: str = "small",
    *,
    model_id: str | None = None,
    region: str | None = None,
    use_reasoning: bool = False,
    reasoning_budget: int | None = None,
    azure_reasoning_effort: str | None = None,
) -> LLMClient:
    """Create an LLM client for the given provider and tier.

    Args:
        provider: ``"aws"`` or ``"azure"``. Defaults to ``PIPELINE_MODEL_PROVIDER`` env var.
        tier: ``"small"``, ``"big"``, or ``"max"``.
        model_id: Explicit model ID (overrides tier lookup).
        region: AWS region (only for Bedrock).
        use_reasoning: Enable reasoning / extended thinking on the model.

            * **AWS Bedrock (Claude)**: passes ``additionalModelRequestFields`` with
              ``{"thinking": {"type": "enabled", "budget_tokens": N}}``.  Forces
              ``temperature=1.0`` (Bedrock hard requirement).  Incompatible with
              ``tool_config`` — tools are silently dropped when both are set.

            * **Azure OpenAI (o-series)**: passes ``reasoning_effort`` (default
              ``"high"``).  Non-o-series deployments that don't support the param
              fall back gracefully to a standard call.

        reasoning_budget: AWS thinking-token budget.  Defaults to a tier-appropriate
            value (small=2000, big=8000, max=10000) from env vars.
        azure_reasoning_effort: Override for the Azure ``reasoning_effort`` value.
            Defaults to ``AZURE_REASONING_EFFORT`` env var (``"high"``).
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

    # Tier-appropriate thinking budget — smaller models don't need 8k thinking tokens.
    budget = reasoning_budget if reasoning_budget is not None else _REASONING_BUDGET_BY_TIER.get(tier, _DEFAULT_REASONING_BUDGET)
    effort = azure_reasoning_effort if azure_reasoning_effort is not None else _AZURE_REASONING_EFFORT

    return LLMClient(
        provider=provider,
        model_id=model_id,
        tier=tier,
        region=region,
        use_reasoning=use_reasoning,
        reasoning_budget=budget,
        azure_reasoning_effort=effort,
    )
