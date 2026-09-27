"""LEO widget SDK analytics ingest endpoint.

Atlas trace:
  DO: DO-23DDE984
  DI: DI-5F121122
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-23DDE984")

POST /sdk/telemetry
    Browser-facing analytics ingest. Deduplicates on
    (widget_instance_id, event_id) so a retried event from the
    widget's backoff queue does not produce a duplicate analytics
    row.

Dedup backend (multi-replica safe):
  Primary:   Azure Managed Redis Enterprise (env REDIS_URL).
             Uses SET NX EX for atomic claim-and-record across
             every API replica that shares the cache.
  Fallback:  In-process bounded LRU. Used when REDIS_URL is unset
             (local dev / CI default) and as a defensive backstop
             when Redis is transiently unreachable, so a network
             blip never causes the API to drop telemetry.

The dedup TTL is hard-coded to 24h. Widget retries cap at ~30s
between attempts, so 24h is comfortably beyond any plausible retry
window without growing the cache unbounded.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sdk", tags=["sdk-telemetry"])

DEDUP_TTL_SECONDS = 24 * 60 * 60
_REDIS_KEY_PREFIX = "sdk:telemetry:dedup:"
_REDIS_CONNECT_TIMEOUT = 2
_REDIS_SOCKET_TIMEOUT = 2

_LRU_CAPACITY = 50_000
_lru_cache: "OrderedDict[tuple[str, int], int]" = OrderedDict()
_event_count = 0

_SENTINEL: Any = object()
_redis_client: Any = _SENTINEL


class TelemetryEvent(BaseModel):
    widget_instance_id: str = Field(..., min_length=1, max_length=128)
    event_id: int = Field(..., ge=1)
    type: Literal[
        "loaded",
        "error",
        "disclosure-opened",
        "disclosure-closed",
        "source-id-clicked",
    ]
    assessment_id: str = Field(..., min_length=1, max_length=128)
    emitted_at_ms: int = Field(..., ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class TelemetryAck(BaseModel):
    status: Literal["accepted", "deduped"]
    widget_instance_id: str
    event_id: int


def _redis_key(key: tuple[str, int]) -> str:
    widget_instance_id, event_id = key
    return f"{_REDIS_KEY_PREFIX}{widget_instance_id}:{event_id}"


def _get_redis_client() -> Any:
    """Lazy Redis client. Returns None if Redis is unconfigured or down."""
    global _redis_client
    if _redis_client is not _SENTINEL:
        return _redis_client

    url = os.getenv("REDIS_URL")
    if not url:
        _redis_client = None
        return None
    try:
        import redis

        client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
            socket_timeout=_REDIS_SOCKET_TIMEOUT,
        )
        client.ping()
        _redis_client = client
    except Exception as exc:
        logger.warning(
            "sdk_telemetry: Redis unavailable, falling back to in-process LRU: %s",
            exc,
        )
        _redis_client = None
    return _redis_client


def _lru_claim(key: tuple[str, int]) -> bool:
    """In-process fallback dedup. Returns True iff this key was already seen."""
    if key in _lru_cache:
        _lru_cache.move_to_end(key)
        return True
    _lru_cache[key] = 1
    while len(_lru_cache) > _LRU_CAPACITY:
        _lru_cache.popitem(last=False)
    return False


def _is_duplicate(key: tuple[str, int]) -> bool:
    """Return True iff (widget_instance_id, event_id) was already accepted.

    Atomic across API replicas when Redis is configured (SET NX EX).
    Falls back to in-process LRU when Redis is unconfigured or down.
    """
    client = _get_redis_client()
    if client is not None:
        try:
            ok = client.set(
                _redis_key(key),
                "1",
                nx=True,
                ex=DEDUP_TTL_SECONDS,
            )
            return ok is None
        except Exception as exc:
            logger.warning(
                "sdk_telemetry: Redis SET NX failed, using LRU fallback: %s",
                exc,
            )
    return _lru_claim(key)


@router.post(
    "/telemetry",
    response_model=TelemetryAck,
    status_code=status.HTTP_200_OK,
)
def ingest_telemetry(event: TelemetryEvent) -> TelemetryAck:
    """Accept a single widget telemetry event with dedupe."""
    global _event_count
    key = (event.widget_instance_id, event.event_id)
    if _is_duplicate(key):
        return TelemetryAck(
            status="deduped",
            widget_instance_id=event.widget_instance_id,
            event_id=event.event_id,
        )
    _event_count += 1
    logger.info(
        "leo widget telemetry accepted: type=%s assessment=%s instance=%s eid=%d",
        event.type,
        event.assessment_id,
        event.widget_instance_id,
        event.event_id,
    )
    return TelemetryAck(
        status="accepted",
        widget_instance_id=event.widget_instance_id,
        event_id=event.event_id,
    )


def _telemetry_counter_for_testing() -> int:
    """Test seam exposing the in-process accepted-event counter."""
    return _event_count


def _reset_telemetry_state_for_testing() -> None:
    """Test seam: clear LRU + counter + cached Redis client between tests.

    Tests that exercise the Redis path should also flush keys under
    _REDIS_KEY_PREFIX from the configured Redis instance.
    """
    global _event_count, _redis_client
    client = None if _redis_client is _SENTINEL else _redis_client
    _lru_cache.clear()
    _event_count = 0
    if client is not None:
        try:
            for key in client.scan_iter(match=f"{_REDIS_KEY_PREFIX}*"):
                client.delete(key)
        except Exception:
            pass
    _redis_client = _SENTINEL


def _set_redis_client_for_testing(client: Any) -> None:
    """Test seam to inject a Redis client double (e.g. an in-memory fake)."""
    global _redis_client
    _redis_client = client
