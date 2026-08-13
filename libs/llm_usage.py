"""LLM token usage tracking and cost calculation.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Bedrock Converse prompt-caching semantics (AWS docs):
  inputTokens = non-cached input only
  total input = inputTokens + cacheReadInputTokens + cacheWriteInputTokens
  Thinking tokens (extended thinking) are included in outputTokens.

Azure OpenAI semantics:
  prompt_tokens = total prompt (includes cached)
  cached portion is in prompt_tokens_details.cached_tokens
  reasoning_tokens are included in completion_tokens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bedrock_cache_read_tokens(usage: dict) -> int:
    """Read Bedrock cache-read tokens across SDK/doc field variants."""
    return int(
        usage.get("cacheReadInputTokens")
        or usage.get("cacheReadInputTokenCount")
        or usage.get("CacheReadInputTokens")
        or usage.get("cache_read_input_tokens")
        or 0
    )


def _bedrock_cache_write_tokens(usage: dict) -> int:
    """Read Bedrock cache-write tokens across SDK/doc field variants."""
    return int(
        usage.get("cacheWriteInputTokens")
        or usage.get("CacheWriteInputTokens")
        or usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_input_tokens")
        or 0
    )


# Baseline per-1M-token cost defaults (USD). Shared with model_config_seed.
# AWS EU cross-region inference profiles = Anthropic base * 1.1.
# Azure Global / Data Zone / Regional Standard meters share the same
# per-token list price; mizaic-cds-oai gpt-5-mini deployment uses these rates.
# Azure has no separate cache-write rate; write defaults to input rate.
# Cache write (5m) = 1.25x input (Anthropic / Bedrock default TTL).
# Sources: azure.com OpenAI pricing, verified 2026-08-10.
COST_DEFAULTS: dict[str, dict[str, dict[str, float]]] = {
    "aws": {
        # eu.anthropic.claude-haiku-4-5
        "small": {
            "input": 1.10,
            "cached": 0.110,
            "cache_write": 1.375,
            "output": 5.50,
        },
        # eu.anthropic.claude-sonnet-4-6
        "big": {
            "input": 3.30,
            "cached": 0.330,
            "cache_write": 4.125,
            "output": 16.50,
        },
        # eu.anthropic.claude-opus-4-6
        "max": {
            "input": 5.50,
            "cached": 0.550,
            "cache_write": 6.875,
            "output": 27.50,
        },
    },
    "azure": {
        # gpt-5-mini deployment on mizaic-cds-oai (Global Standard pricing)
        "small": {
            "input": 0.75,
            "cached": 0.075,
            "cache_write": 0.75,
            "output": 4.50,
        },
        # gpt-5.4 Global Standard (<272k context)
        "big": {
            "input": 2.50,
            "cached": 0.25,
            "cache_write": 2.50,
            "output": 15.00,
        },
    },
}

# Back-compat alias for internal lookups.
_COST_DEFAULTS = COST_DEFAULTS


@dataclass(frozen=True)
class LLMCostConfig:
    """Per-token cost rates loaded from environment variables."""

    cost_per_1m_input: float
    cost_per_1m_cached_input: float
    cost_per_1m_output: float
    cost_per_1m_cache_write: float = 0.0

    @classmethod
    def from_env(cls) -> LLMCostConfig:
        tier = os.getenv("PIPELINE_MODEL_TIER", "small").strip()
        return cls.for_tier(tier)

    @classmethod
    def for_tier(cls, tier: str) -> LLMCostConfig:
        """Resolve cost rates for an explicit tier (small/big/max)."""
        provider = os.getenv("PIPELINE_MODEL_PROVIDER", "azure").strip().lower()
        return cls.for_provider_tier(provider, tier)

    @classmethod
    def for_provider_tier(cls, provider: str, tier: str) -> LLMCostConfig:
        """Resolve cost rates for an explicit provider and tier."""
        provider_lc = (provider or "azure").strip().lower()
        tier_lc = (tier or "small").strip().lower()
        tier_up = tier_lc.upper()
        if provider_lc == "azure":
            prefix = f"AZURE_OPENAI_{tier_up}_MODEL"
        else:
            prefix = f"AWS_BEDROCK_MODEL_{tier_up}_MODEL"

        defaults = _COST_DEFAULTS.get(provider_lc, {}).get(
            tier_lc,
            {"input": 0.0, "cached": 0.0, "cache_write": 0.0, "output": 0.0},
        )
        input_rate = float(
            os.getenv(f"{prefix}_COST_PER_1M_INPUT_TOKEN", str(defaults["input"]))
        )
        write_default = defaults.get("cache_write", input_rate * 1.25)
        return cls(
            cost_per_1m_input=input_rate,
            cost_per_1m_cached_input=float(
                os.getenv(
                    f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN",
                    str(defaults["cached"]),
                )
            ),
            cost_per_1m_output=float(
                os.getenv(f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", str(defaults["output"]))
            ),
            cost_per_1m_cache_write=float(
                os.getenv(
                    f"{prefix}_COST_PER_1M_CACHE_WRITE_TOKEN",
                    str(write_default),
                )
            ),
        )


def infer_model_tier(model_name: str) -> str:
    """Map a provider model id to small/big/max. Empty if unknown."""
    name = (model_name or "").strip().lower()
    if not name:
        return ""
    if "haiku" in name or "nano" in name or "mini" in name:
        return "small"
    if "opus" in name:
        return "max"
    if "sonnet" in name or "gpt-5" in name:
        return "big"
    return ""


def _canonical_provider(provider: str, model_name: str) -> str:
    p = (provider or "").strip().lower()
    if p in ("aws", "bedrock"):
        return "aws"
    if p == "azure":
        return "azure"
    name = (model_name or "").lower()
    claude_tags = ("anthropic", "claude", "haiku", "sonnet", "opus")
    if any(tag in name for tag in claude_tags):
        return "aws"
    return "azure" if name else p


def cost_config_for_invocation(
    provider: str = "",
    tier: str = "",
    model_name: str = "",
    fallback: LLMCostConfig | None = None,
) -> LLMCostConfig:
    """Resolve list-price rates for one LLM call, not the env default tier."""
    provider_lc = _canonical_provider(provider, model_name)
    tier_lc = (tier or "").strip().lower()
    if tier_lc not in ("small", "big", "max"):
        tier_lc = infer_model_tier(model_name)
    if provider_lc in ("aws", "azure") and tier_lc in ("small", "big", "max"):
        return LLMCostConfig.for_provider_tier(provider_lc, tier_lc)
    if fallback is not None:
        return fallback
    return LLMCostConfig.from_env()


@dataclass
class LLMUsage:
    """Accumulator for LLM token counts across one or more API calls.

    ``input_excludes_cache``:
      True  -- Bedrock Converse: ``input_tokens`` is non-cached only.
      False -- Azure-style: ``input_tokens`` is total prompt including cache.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    llm_calls: int = 0
    input_excludes_cache: bool = False
    reasoning_tokens: int = 0
    _cost_config: LLMCostConfig | None = field(default=None, repr=False)

    @classmethod
    def from_bedrock_response(cls, response: dict) -> LLMUsage:
        usage = response.get("usage", {})
        return cls(
            input_tokens=int(usage.get("inputTokens", 0) or 0),
            output_tokens=int(usage.get("outputTokens", 0) or 0),
            cached_input_tokens=_bedrock_cache_read_tokens(usage),
            cache_creation_input_tokens=_bedrock_cache_write_tokens(usage),
            llm_calls=1,
            input_excludes_cache=True,
        )

    @classmethod
    def zero(cls) -> LLMUsage:
        return cls()

    def __iadd__(self, other: LLMUsage) -> LLMUsage:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.llm_calls += other.llm_calls
        self.input_excludes_cache = (
            self.input_excludes_cache or other.input_excludes_cache
        )
        return self

    def __add__(self, other: LLMUsage) -> LLMUsage:
        return LLMUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            llm_calls=self.llm_calls + other.llm_calls,
            input_excludes_cache=(
                self.input_excludes_cache or other.input_excludes_cache
            ),
        )

    @property
    def total_tokens(self) -> int:
        if self.input_excludes_cache:
            return (
                self.input_tokens
                + self.cached_input_tokens
                + self.cache_creation_input_tokens
                + self.output_tokens
            )
        return self.input_tokens + self.output_tokens

    def _full_rate_input_tokens(self) -> int:
        if self.input_excludes_cache:
            return max(0, int(self.input_tokens))
        return max(0, int(self.input_tokens) - int(self.cached_input_tokens))

    def cost_usd(self, config: LLMCostConfig | None = None) -> float:
        cfg = config or self._cost_config
        if cfg is None:
            return 0.0
        write_rate = cfg.cost_per_1m_cache_write or (cfg.cost_per_1m_input * 1.25)
        return (
            self._full_rate_input_tokens() * cfg.cost_per_1m_input / 1_000_000
            + self.cached_input_tokens * cfg.cost_per_1m_cached_input / 1_000_000
            + self.cache_creation_input_tokens * write_rate / 1_000_000
            + self.output_tokens * cfg.cost_per_1m_output / 1_000_000
        )

    def to_dict(self, config: LLMCostConfig | None = None) -> dict:
        cfg = config or self._cost_config
        d: dict = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "input_excludes_cache": self.input_excludes_cache,
        }
        if cfg:
            d["cost_usd"] = round(self.cost_usd(cfg), 6)
        return d
