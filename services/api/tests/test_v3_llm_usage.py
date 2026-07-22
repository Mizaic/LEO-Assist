"""Tests for LLM usage tracking and cost calculation."""

from __future__ import annotations

from app.services.llm_usage import LLMCostConfig, LLMUsage


class TestLLMUsage:

    def test_zero(self) -> None:
        u = LLMUsage.zero()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.llm_calls == 0
        assert u.total_tokens == 0

    def test_from_bedrock_response(self) -> None:
        resp = {"usage": {"inputTokens": 500, "outputTokens": 100}}
        u = LLMUsage.from_bedrock_response(resp)
        assert u.input_tokens == 500
        assert u.output_tokens == 100
        assert u.llm_calls == 1
        assert u.total_tokens == 600

    def test_from_bedrock_response_with_cache(self) -> None:
        resp = {
            "usage": {
                "inputTokens": 500,
                "outputTokens": 100,
                "cacheReadInputTokenCount": 200,
            }
        }
        u = LLMUsage.from_bedrock_response(resp)
        assert u.cached_input_tokens == 200

    def test_from_bedrock_response_with_cache_tokens_key(self) -> None:
        resp = {
            "usage": {
                "inputTokens": 500,
                "outputTokens": 100,
                "cacheReadInputTokens": 220,
            }
        }
        u = LLMUsage.from_bedrock_response(resp)
        assert u.cached_input_tokens == 220

    def test_add(self) -> None:
        a = LLMUsage(input_tokens=100, output_tokens=50, llm_calls=1)
        b = LLMUsage(input_tokens=200, output_tokens=80, llm_calls=1)
        c = a + b
        assert c.input_tokens == 300
        assert c.output_tokens == 130
        assert c.llm_calls == 2
        assert c.total_tokens == 430

    def test_iadd(self) -> None:
        a = LLMUsage(input_tokens=100, output_tokens=50, llm_calls=1)
        a += LLMUsage(input_tokens=200, output_tokens=80, llm_calls=1)
        assert a.input_tokens == 300
        assert a.llm_calls == 2

    def test_cost_usd_no_cache(self) -> None:
        cfg = LLMCostConfig(
            cost_per_1m_input=1.0,
            cost_per_1m_cached_input=0.01,
            cost_per_1m_output=5.0,
        )
        u = LLMUsage(input_tokens=1_000_000, output_tokens=100_000, llm_calls=5)
        cost = u.cost_usd(cfg)
        assert cost == 1.0 + 0.5  # 1M input * $1 + 100K output * $5

    def test_cost_usd_with_cache_azure_style(self) -> None:
        """Azure: input_tokens includes cached; subtract before full rate."""
        cfg = LLMCostConfig(
            cost_per_1m_input=1.0,
            cost_per_1m_cached_input=0.10,
            cost_per_1m_output=5.0,
        )
        u = LLMUsage(
            input_tokens=1_000_000,
            output_tokens=100_000,
            cached_input_tokens=400_000,
            llm_calls=5,
            input_excludes_cache=False,
        )
        cost = u.cost_usd(cfg)
        # billable_input = 600K * $1/1M = $0.60
        # cached = 400K * $0.10/1M = $0.04
        # output = 100K * $5/1M = $0.50
        expected = 0.60 + 0.04 + 0.50
        assert abs(cost - expected) < 1e-6

    def test_cost_usd_bedrock_no_double_subtract(self) -> None:
        """Bedrock: input_tokens is non-cached only; do not subtract cache."""
        cfg = LLMCostConfig(
            cost_per_1m_input=1.0,
            cost_per_1m_cached_input=0.10,
            cost_per_1m_cache_write=1.25,
            cost_per_1m_output=5.0,
        )
        u = LLMUsage(
            input_tokens=600_000,
            output_tokens=100_000,
            cached_input_tokens=400_000,
            cache_creation_input_tokens=50_000,
            llm_calls=1,
            input_excludes_cache=True,
        )
        cost = u.cost_usd(cfg)
        # full input 600K * $1 = $0.60
        # cache read 400K * $0.10 = $0.04
        # cache write 50K * $1.25 = $0.0625
        # output 100K * $5 = $0.50
        expected = 0.60 + 0.04 + 0.0625 + 0.50
        assert abs(cost - expected) < 1e-6
        assert u.total_tokens == 1_150_000

    def test_from_bedrock_response_cache_write(self) -> None:
        resp = {
            "usage": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 50,
                "cacheWriteInputTokens": 30,
            }
        }
        u = LLMUsage.from_bedrock_response(resp)
        assert u.cached_input_tokens == 50
        assert u.cache_creation_input_tokens == 30
        assert u.input_excludes_cache is True
        assert u.total_tokens == 200

    def test_cost_usd_no_config_returns_zero(self) -> None:
        u = LLMUsage(input_tokens=1000, output_tokens=500, llm_calls=1)
        assert u.cost_usd() == 0.0

    def test_to_dict(self) -> None:
        cfg = LLMCostConfig(
            cost_per_1m_input=1.0,
            cost_per_1m_cached_input=0.01,
            cost_per_1m_output=5.0,
        )
        u = LLMUsage(input_tokens=1000, output_tokens=500, llm_calls=2)
        d = u.to_dict(cfg)
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 500
        assert d["total_tokens"] == 1500
        assert d["llm_calls"] == 2
        assert "cost_usd" in d

    def test_to_dict_without_config(self) -> None:
        u = LLMUsage(input_tokens=100, output_tokens=50, llm_calls=1)
        d = u.to_dict()
        assert "cost_usd" not in d
        assert d["total_tokens"] == 150


class TestLLMCostConfig:

    def test_from_env_defaults(self, monkeypatch) -> None:
        monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "aws")
        monkeypatch.setenv("PIPELINE_MODEL_TIER", "small")
        monkeypatch.setenv(
            "AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_INPUT_TOKEN", "1.00"
        )
        monkeypatch.setenv(
            "AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_CACHED_INPUT_TOKEN", "0.01"
        )
        monkeypatch.setenv(
            "AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_OUTPUT_TOKEN", "5.00"
        )
        cfg = LLMCostConfig.from_env()
        assert cfg.cost_per_1m_input == 1.0
        assert cfg.cost_per_1m_cached_input == 0.01
        assert cfg.cost_per_1m_output == 5.0

    def test_from_env_azure(self, monkeypatch) -> None:
        monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
        monkeypatch.setenv("PIPELINE_MODEL_TIER", "big")
        monkeypatch.setenv("AZURE_OPENAI_BIG_MODEL_COST_PER_1M_INPUT_TOKEN", "1.25")
        monkeypatch.setenv(
            "AZURE_OPENAI_BIG_MODEL_COST_PER_1M_CACHED_INPUT_TOKEN", "0.13"
        )
        monkeypatch.setenv("AZURE_OPENAI_BIG_MODEL_COST_PER_1M_OUTPUT_TOKEN", "10")
        cfg = LLMCostConfig.from_env()
        assert cfg.cost_per_1m_input == 1.25
        assert cfg.cost_per_1m_output == 10.0
