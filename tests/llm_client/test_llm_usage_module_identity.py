"""VT-LEO-AI-518 TC-002: LLMUsage / LLMCostConfig module identity.

DI-LEO-AI-519 consolidates the two previously divergent ``LLMUsage`` /
``LLMCostConfig`` implementations into a single canonical module at
``libs.llm_usage``. The ``services.api.app.services.llm_usage`` module
remains as a thin re-export so existing call sites continue to work.

These tests assert that ``LLMUsage`` and ``LLMCostConfig`` imported from
either path resolve to the exact same class object so cost numbers no
longer depend on which import path the caller happened to use.
"""

from __future__ import annotations


def test_llm_usage_class_is_identical_across_import_paths() -> None:
    from libs.llm_usage import LLMUsage as LibsLLMUsage
    from services.api.app.services.llm_usage import LLMUsage as ServiceLLMUsage

    assert LibsLLMUsage is ServiceLLMUsage


def test_llm_cost_config_class_is_identical_across_import_paths() -> None:
    from libs.llm_usage import LLMCostConfig as LibsLLMCostConfig
    from services.api.app.services.llm_usage import (
        LLMCostConfig as ServiceLLMCostConfig,
    )

    assert LibsLLMCostConfig is ServiceLLMCostConfig


def test_bedrock_cache_read_tokens_helper_is_re_exported() -> None:
    from libs.llm_usage import _bedrock_cache_read_tokens as libs_helper
    from services.api.app.services.llm_usage import (
        _bedrock_cache_read_tokens as service_helper,
    )

    assert libs_helper is service_helper
