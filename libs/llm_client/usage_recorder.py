"""Per-run LLM usage accumulator scoped via contextvars.

Any orchestrator can wrap a logical run in
``with LLMUsageRecorder() as rec: ...`` and every nested
``invoke_llm_json`` call inside that block will be recorded into the
recorder. Concurrent asyncio tasks each get an isolated copy thanks
to ``contextvars.ContextVar``.

A default tracking callback is registered with
``libs.llm_client.token_tracker.set_tracking_callback`` on first import,
so callers do not need to wire anything up manually.

Usage:

    from libs.llm_client.usage_recorder import LLMUsageRecorder
    from libs.llm_usage import LLMCostConfig

    cfg = LLMCostConfig.from_env()
    with LLMUsageRecorder() as rec:
        await invoke_llm_json(...)
        await invoke_llm_json(...)

    print(rec.usage.input_tokens, rec.cost_usd(cfg), rec.calls)
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from libs.llm_client.token_tracker import set_tracking_callback
from libs.llm_usage import LLMCostConfig, LLMUsage

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    """One row per LLM invocation that completed (success or failure)."""

    agent_task: str
    model_name: str
    model_provider: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: int
    success: bool
    error_message: str = ""
    patient_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_task": self.agent_task,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error_message": self.error_message,
            "patient_id": self.patient_id,
        }


@dataclass
class LLMUsageRecorder:
    """Context-scoped accumulator for nested ``invoke_llm_json`` calls."""

    usage: LLMUsage = field(default_factory=LLMUsage.zero)
    calls: List[LLMCallRecord] = field(default_factory=list)
    total_latency_ms: int = 0
    primary_model: str = ""
    primary_provider: str = ""

    _token: Optional[contextvars.Token] = field(default=None, repr=False)

    def __enter__(self) -> "LLMUsageRecorder":
        self._token = _ACTIVE_RECORDER.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _ACTIVE_RECORDER.reset(self._token)
            self._token = None

    def record(self, call: LLMCallRecord) -> None:
        """Add a single LLM call to this recorder."""
        self.calls.append(call)
        self.total_latency_ms += int(call.latency_ms or 0)
        self.usage += LLMUsage(
            input_tokens=int(call.input_tokens),
            output_tokens=int(call.output_tokens),
            cached_input_tokens=int(call.cached_input_tokens),
            llm_calls=1,
        )
        if not self.primary_model and call.model_name:
            self.primary_model = call.model_name
        if not self.primary_provider and call.model_provider:
            self.primary_provider = call.model_provider

    def cost_usd(self, config: LLMCostConfig | None = None) -> float:
        """Return the rolled-up cost for everything recorded so far."""
        return round(self.usage.cost_usd(config), 6)

    def to_audit_dict(self, config: LLMCostConfig | None = None) -> dict[str, Any]:
        """Return a dictionary shaped for the AuditEvent / Assessment writes."""
        return {
            "input_tokens": int(self.usage.input_tokens),
            "output_tokens": int(self.usage.output_tokens),
            "cached_input_tokens": int(self.usage.cached_input_tokens),
            "total_tokens": int(self.usage.total_tokens),
            "llm_calls": int(self.usage.llm_calls),
            "total_latency_ms": int(self.total_latency_ms),
            "model_name": self.primary_model,
            "model_provider": self.primary_provider,
            "cost_usd": self.cost_usd(config),
        }


_ACTIVE_RECORDER: contextvars.ContextVar[Optional[LLMUsageRecorder]] = (
    contextvars.ContextVar("llm_usage_recorder", default=None)
)


def get_active_recorder() -> Optional[LLMUsageRecorder]:
    """Return the recorder bound to the current async context, or None."""
    return _ACTIVE_RECORDER.get()


def _default_tracking_callback(**kwargs: Any) -> None:
    """Forward LLM usage from invoke_llm_json into the active recorder.

    Mapped from ``track_llm_usage`` keyword arguments to a
    ``LLMCallRecord``. Cache-creation and cache-read tokens (Bedrock)
    are added together for the recorder's ``cached_input_tokens`` field;
    the same convention is used by ``LLMUsage.from_bedrock_response``.
    """
    rec = _ACTIVE_RECORDER.get()
    if rec is None:
        return
    try:
        cached = int(kwargs.get("cache_read_input_tokens") or 0) + int(
            kwargs.get("cache_creation_input_tokens") or 0
        )
        rec.record(
            LLMCallRecord(
                agent_task=str(kwargs.get("agent_task") or ""),
                model_name=str(kwargs.get("model_name") or ""),
                model_provider=str(kwargs.get("model_provider") or ""),
                input_tokens=int(kwargs.get("input_tokens") or 0),
                output_tokens=int(kwargs.get("output_tokens") or 0),
                cached_input_tokens=cached,
                latency_ms=int(kwargs.get("latency_ms") or 0),
                success=bool(kwargs.get("success", True)),
                error_message=str(kwargs.get("error_message") or ""),
                patient_id=str(kwargs.get("patient_id") or ""),
            )
        )
    except Exception:
        logger.debug("LLMUsageRecorder default callback failed", exc_info=True)


set_tracking_callback(_default_tracking_callback)
