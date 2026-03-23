"""LLM token usage tracking and cost calculation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bedrock_cache_read_tokens(usage: dict) -> int:
    """Read Bedrock cache-read tokens across SDK/doc field variants."""
    return int(
        usage.get("cacheReadInputTokens")
        or usage.get("cacheReadInputTokenCount")
        or usage.get("CacheReadInputTokens")
        or 0
    )


@dataclass(frozen=True)
class LLMCostConfig:
    """Per-token cost rates loaded from environment variables."""

    cost_per_1m_input: float
    cost_per_1m_cached_input: float
    cost_per_1m_output: float

    @classmethod
    def from_env(cls) -> LLMCostConfig:
        provider = os.getenv("PIPELINE_MODEL_PROVIDER", "aws").strip().lower()
        tier = os.getenv("PIPELINE_MODEL_TIER", "small").strip().upper()

        if provider == "azure":
            prefix = f"AZURE_OPENAI_{tier}_MODEL"
        else:
            prefix = f"AWS_BEDROCK_MODEL_{tier}_MODEL"

        return cls(
            cost_per_1m_input=float(
                os.getenv(f"{prefix}_COST_PER_1M_INPUT_TOKEN", "0")
            ),
            cost_per_1m_cached_input=float(
                os.getenv(f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN", "0")
            ),
            cost_per_1m_output=float(
                os.getenv(f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", "0")
            ),
        )


@dataclass
class LLMUsage:
    """Accumulator for LLM token counts across one or more API calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    llm_calls: int = 0
    _cost_config: LLMCostConfig | None = field(default=None, repr=False)

    @classmethod
    def from_bedrock_response(cls, response: dict) -> LLMUsage:
        usage = response.get("usage", {})
        return cls(
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            cached_input_tokens=_bedrock_cache_read_tokens(usage),
            llm_calls=1,
        )

    @classmethod
    def zero(cls) -> LLMUsage:
        return cls()

    def __iadd__(self, other: LLMUsage) -> LLMUsage:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.llm_calls += other.llm_calls
        return self

    def __add__(self, other: LLMUsage) -> LLMUsage:
        return LLMUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            llm_calls=self.llm_calls + other.llm_calls,
        )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def cost_usd(self, config: LLMCostConfig | None = None) -> float:
        cfg = config or self._cost_config
        if cfg is None:
            return 0.0
        billable_input = max(0, self.input_tokens - self.cached_input_tokens)
        return (
            billable_input * cfg.cost_per_1m_input / 1_000_000
            + self.cached_input_tokens * cfg.cost_per_1m_cached_input / 1_000_000
            + self.output_tokens * cfg.cost_per_1m_output / 1_000_000
        )

    def to_dict(self, config: LLMCostConfig | None = None) -> dict:
        cfg = config or self._cost_config
        d: dict = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
        }
        if cfg:
            d["cost_usd"] = round(self.cost_usd(cfg), 6)
        return d
