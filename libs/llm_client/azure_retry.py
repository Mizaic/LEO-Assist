"""Retry transient Azure OpenAI failures.

Chat Completions already retries timeouts. The Responses path did not,
so one slow GPT-5 window could wipe every fact from a letter.

Atlas trace:
  DI: DI-7B978C0C
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-7B978C0C")
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_BASE_DELAY_S = 1.0
_MAX_DELAY_S = 30.0


def _retry_delay_s(attempt: int) -> float:
    """Return backoff seconds for this 1-based attempt."""
    return min(_MAX_DELAY_S, _BASE_DELAY_S * (2 ** (attempt - 1))) + random.uniform(
        0, 0.5
    )


def _sleep_before_retry(
    *,
    model_id: str,
    kind: str,
    elapsed: float,
    attempt: int,
    max_retries: int,
    detail: str = "",
) -> None:
    delay = _retry_delay_s(attempt)
    extra = f" {detail}" if detail else ""
    logger.warning(
        "Azure %s: %s after %.1fs on attempt %d/%d -- retrying in %.1fs.%s",
        model_id,
        kind,
        elapsed,
        attempt,
        max_retries,
        delay,
        extra,
    )
    time.sleep(delay)


def _retry_or_raise(
    exc: BaseException,
    *,
    model_id: str,
    kind: str,
    started: float,
    attempt: int,
    max_retries: int,
    retry: bool,
    detail: str = "",
) -> None:
    elapsed = time.monotonic() - started
    if not retry or attempt == max_retries:
        logger.error(
            "Azure %s: %s after %.1fs on final attempt %d/%d.",
            model_id,
            kind,
            elapsed,
            attempt,
            max_retries,
        )
        raise exc
    _sleep_before_retry(
        model_id=model_id,
        kind=kind,
        elapsed=elapsed,
        attempt=attempt,
        max_retries=max_retries,
        detail=detail,
    )


def call_azure_with_retry(
    operation: Callable[[], T],
    *,
    model_id: str,
    max_retries: int = _MAX_RETRIES,
) -> T:
    """Run one Azure HTTP call and retry timeouts and short outages."""
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    for attempt in range(1, max_retries + 1):
        started = time.monotonic()
        try:
            return operation()
        except APITimeoutError as exc:
            _retry_or_raise(
                exc,
                model_id=model_id,
                kind="TIMEOUT",
                started=started,
                attempt=attempt,
                max_retries=max_retries,
                retry=True,
            )
        except APIConnectionError as exc:
            _retry_or_raise(
                exc,
                model_id=model_id,
                kind="CONNECTION ERROR",
                started=started,
                attempt=attempt,
                max_retries=max_retries,
                retry=True,
                detail=str(exc),
            )
        except APIStatusError as exc:
            retry = attempt < max_retries and exc.status_code in _RETRYABLE_STATUS
            _retry_or_raise(
                exc,
                model_id=model_id,
                kind=f"HTTP {exc.status_code}",
                started=started,
                attempt=attempt,
                max_retries=max_retries,
                retry=retry,
            )
    raise RuntimeError("Azure retry loop exited without a result")
