"""Shared LLM client library with caching, retry, and fallback support.

Combines:
- LLM response caching (from auditor_2 core/llm_cache.py)
- Bedrock + Azure fallback strategy (from auditor_2 core/models.py)
- Token tracking
"""

from libs.llm_client.cache import (
    InMemoryLLMCache,
    get_llm_cache,
    clear_llm_cache,
    get_cache_stats,
    cached_llm_invoke,
    messages_to_dict,
)
from libs.llm_client.providers import (
    get_bedrock_model,
    get_azure_model,
    invoke_with_retry,
    invoke_with_fallback,
)
from libs.llm_client.factory import create_llm, LLMClient, LLMResponse
from libs.llm_client.json_helper import invoke_llm_json
from libs.llm_client.token_tracker import extract_token_counts, track_llm_usage

__all__ = [
    "InMemoryLLMCache",
    "get_llm_cache",
    "clear_llm_cache",
    "get_cache_stats",
    "cached_llm_invoke",
    "messages_to_dict",
    "get_bedrock_model",
    "get_azure_model",
    "invoke_with_retry",
    "invoke_with_fallback",
    "invoke_llm_json",
    "extract_token_counts",
    "track_llm_usage",
    "create_llm",
    "LLMClient",
    "LLMResponse",
]
