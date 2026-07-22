"""Process-wide Bedrock boto3 client factory with sized connection pools.

Each boto3 ``bedrock-runtime`` client owns an urllib3 connection pool. The
default pool size is 10, which is too small when the pipeline worker handles
several Service Bus messages concurrently and each step may issue overlapping
Bedrock Converse calls (consensus panels, parallel SBAR sections, tool loops).

Tune via ``BEDROCK_MAX_POOL_CONNECTIONS``. When unset, the default scales with
``SB_MAX_CONCURRENT_CALLS`` (pipeline worker message concurrency).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


def bedrock_max_pool_connections() -> int:
    """Return urllib3 ``max_pool_connections`` for bedrock-runtime clients."""
    raw = os.getenv("BEDROCK_MAX_POOL_CONNECTIONS", "").strip()
    if raw:
        return max(1, int(raw))
    sb_concurrent = max(1, int(os.getenv("SB_MAX_CONCURRENT_CALLS", "8")))
    # Each handler may run several overlapping Bedrock calls; 4x SB concurrency
    # with a floor of 32 covers validation-lab / multi-step pipeline bursts.
    return max(32, sb_concurrent * 4)


def _bedrock_botocore_config(
    *,
    connect_timeout: int,
    read_timeout: int,
    max_attempts: int,
    tcp_keepalive: bool,
) -> Any:
    from botocore.config import Config

    return Config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_attempts, "mode": "standard"},
        tcp_keepalive=tcp_keepalive,
        max_pool_connections=bedrock_max_pool_connections(),
    )


@lru_cache(maxsize=8)
def get_bedrock_runtime_client(
    region: str,
    connect_timeout: int,
    read_timeout: int,
    max_attempts: int,
    tcp_keepalive: bool,
) -> Any:
    """Return a cached boto3 bedrock-runtime client for the given config."""
    import boto3

    cfg = _bedrock_botocore_config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_attempts=max_attempts,
        tcp_keepalive=tcp_keepalive,
    )
    return boto3.client("bedrock-runtime", region_name=region, config=cfg)


def reset_bedrock_client_cache() -> None:
    """Clear cached Bedrock boto3 clients (test hook)."""
    get_bedrock_runtime_client.cache_clear()
