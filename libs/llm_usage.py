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


# Baseline per-1M-token cost defaults, mirroring
# services/api/app/services/model_config_seed.py. EU cross-region inference
# profile rates verified 2026-03-08. Override at runtime via env vars.
_COST_DEFAULTS: dict[str, dict[str, dict[str, float]]] = {
    "aws": {
        # eu.anthropic.claude-haiku-4-5
        "small": {"input": 1.10, "cached": 0.110, "output": 5.50},
        # eu.anthropic.claude-sonnet-4-6
        "big": {"input": 3.30, "cached": 0.330, "output": 16.50},
        # eu.anthropic.claude-opus-4-6
        "max": {"input": 5.50, "cached": 0.550, "output": 27.50},
    },
    "azure": {
        # azure/eu/gpt-5-mini
        "small": {"input": 0.275, "cached": 0.028, "output": 2.20},
        # azure/eu/gpt-5
        "big": {"input": 1.375, "cached": 0.138, "output": 11.00},
    },
}


@dataclass(frozen=True)
class LLMCostConfig:
    """Per-token cost rates loaded from environment variables."""

    cost_per_1m_input: float
    cost_per_1m_cached_input: float
    cost_per_1m_output: float

    @classmethod
    def from_env(cls) -> LLMCostConfig:
        tier = os.getenv("PIPELINE_MODEL_TIER", "small").strip()
        return cls.for_tier(tier)

    @classmethod
    def for_tier(cls, tier: str) -> LLMCostConfig:
        """Resolve cost rates for an explicit tier (small/big/max).

        Reads the same env-var convention as ``from_env`` but lets the
        caller specify the tier directly -- needed by callers that mix
        multiple tiers in a single workflow (e.g. the episode engine
        runs Haiku for stages 1-4 and Sonnet for the reconciler).

        If the env vars are not set, falls back to the same EU-region
        baseline defaults used by ``services/api/app/services/
        model_config_seed.py`` so cost calculations work out of the box.
        """

        provider = os.getenv("PIPELINE_MODEL_PROVIDER", "aws").strip().lower()
        tier_lc = (tier or "small").strip().lower()
        tier_up = tier_lc.upper()
        if provider == "azure":
            prefix = f"AZURE_OPENAI_{tier_up}_MODEL"
        else:
            prefix = f"AWS_BEDROCK_MODEL_{tier_up}_MODEL"

        defaults = _COST_DEFAULTS.get(provider, {}).get(
            tier_lc, {"input": 0.0, "cached": 0.0, "output": 0.0}
        )
        return cls(
            cost_per_1m_input=float(
                os.getenv(
                    f"{prefix}_COST_PER_1M_INPUT_TOKEN", str(defaults["input"])
                )
            ),
            cost_per_1m_cached_input=float(
                os.getenv(
                    f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN",
                    str(defaults["cached"]),
                )
            ),
            cost_per_1m_output=float(
                os.getenv(
                    f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", str(defaults["output"])
                )
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
