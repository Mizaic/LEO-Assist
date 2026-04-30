"""Exponential backoff retry for AWS Bedrock API calls.

Atlas trace:
  DO: DO-7123C55A
  DI: DI-AE7680C0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-7123C55A")

Retries on 429/throttling and transient server errors so the pipeline
does not fail or skip encounters when rate-limited.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)

# Bedrock/boto3 error codes that warrant retry with backoff
_THROTTLE_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelTimeoutException",  # Bedrock-specific
    }
)


def _get_error_code(exc: BaseException) -> str:
    """Extract AWS error code from ClientError."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return ""
    if not isinstance(exc, ClientError):
        return ""
    response = getattr(exc, "response", None) or {}
    return str((response.get("Error") or {}).get("Code", ""))


def _is_retryable(exc: BaseException) -> bool:
    if _get_error_code(exc) in _THROTTLE_CODES:
        return True
    # Also retry on network-level timeouts — a hung TCP connection (no bytes
    # received within read_timeout) raises ReadTimeoutError, which is not a
    # ClientError but is equally transient.
    exc_type = type(exc).__name__
    return exc_type in {"ReadTimeoutError", "ConnectTimeoutError", "ConnectionError"}


def converse_with_retry(
    client: Any,
    *,
    model_id: str,
    max_retries: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
    **converse_kwargs: Any,
) -> dict[str, Any]:
    """Call client.converse() with exponential backoff on throttle/429.

    Retries on ThrottlingException, TooManyRequestsException, ServiceUnavailableException,
    etc. Does not retry on validation errors or other non-transient failures.

    Args:
        client: boto3 bedrock-runtime client
        model_id: Bedrock model ID
        max_retries: Max attempts (default 8)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Cap on delay in seconds (default 60.0)
        jitter: Random jitter range in seconds (default 0.5)
        **converse_kwargs: Passed to client.converse() (system, messages, inferenceConfig, etc.)

    Returns:
        Raw Bedrock converse response dict

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return client.converse(modelId=model_id, **converse_kwargs)
        except BaseException as exc:
            last_exc = exc
            if not _is_retryable(exc) or attempt == max_retries - 1:
                raise
            sleep_s = min(max_delay, base_delay * (2**attempt)) + random.uniform(
                0, jitter
            )
            code = _get_error_code(exc) or "Unknown"
            logger.warning(
                "Bedrock throttle (attempt %d/%d): %s, retrying in %.1fs",
                attempt + 1,
                max_retries,
                code,
                sleep_s,
            )
            time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Bedrock request failed after retries")
