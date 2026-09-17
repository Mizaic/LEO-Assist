"""Per-run LLM usage accumulator scoped via contextvars.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

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

Design decision (2026-07 CTO peer-review item 3, Phase B): do NOT wrap
``WorkflowEngine`` (libs/workflow/engine.py) in ``LLMUsageRecorder``.
``WorkflowEngine._write_audit_event`` already sums
``llm_input_tokens``/``llm_output_tokens``/``llm_cached_tokens``/
``llm_cost_usd`` directly from its own ``StepResult`` subgraph outputs and
writes them onto the ``AuditEvent {type:'PipelineRun'}`` node -- that
manual summation is the coding path's source of truth today, and it is
what powers `/pricing/orgs`, `/analytics/llm-spend/runs`, and (as of the
Phase A query extension) `/analytics/llm-spend/patient`.

Adding an ``LLMUsageRecorder`` around the same run would create a SECOND,
independent accumulator with no reconciliation between the two, risking
silent double-counting or drift if they ever disagree (e.g. a step that
updates ``StepResult`` fields without also being inside the recorder's
active scope, or vice versa). Reserve ``LLMUsageRecorder`` for
orchestrators that do not already aggregate their own token totals (the
SBAR orchestrator, `services/analysis_worker/.../sbar_orchestrator.py`,
is the reference implementation this class was built for). If a future
change needs the recorder's per-call `agent_task`/`patient_id` breakdown
inside WorkflowEngine, it must REMOVE the manual summation in the same
change -- never run both accumulators at once for the same run.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from libs.llm_client.token_tracker import set_tracking_callback
from libs.llm_usage import LLMCostConfig, LLMUsage, cost_config_for_invocation

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
    cache_creation_input_tokens: int = 0
    reasoning_tokens: int = 0
    input_excludes_cache: bool = False
    model_tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_task": self.agent_task,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "model_tier": self.model_tier,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "input_excludes_cache": self.input_excludes_cache,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error_message": self.error_message,
            "patient_id": self.patient_id,
        }


def _usage_from_call(call: LLMCallRecord) -> LLMUsage:
    return LLMUsage(
        input_tokens=int(call.input_tokens),
        output_tokens=int(call.output_tokens),
        cached_input_tokens=int(call.cached_input_tokens),
        cache_creation_input_tokens=int(call.cache_creation_input_tokens),
        reasoning_tokens=int(call.reasoning_tokens),
        llm_calls=1,
        input_excludes_cache=bool(call.input_excludes_cache),
    )


def _call_cost_usd(call: LLMCallRecord, fallback: LLMCostConfig | None = None) -> float:
    cfg = cost_config_for_invocation(
        call.model_provider, call.model_tier, call.model_name, fallback
    )
    return _usage_from_call(call).cost_usd(cfg)


@dataclass
class LLMUsageRecorder:
    """Context-scoped accumulator for nested ``invoke_llm_json`` calls."""

    usage: LLMUsage = field(default_factory=LLMUsage.zero)
    calls: List[LLMCallRecord] = field(default_factory=list)
    total_latency_ms: int = 0
    primary_model: str = ""
    primary_provider: str = ""

    _token: Optional[contextvars.Token] = field(default=None, repr=False)
    _parent: Optional["LLMUsageRecorder"] = field(default=None, repr=False)

    def __enter__(self) -> "LLMUsageRecorder":
        self._parent = _ACTIVE_RECORDER.get()
        self._token = _ACTIVE_RECORDER.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _ACTIVE_RECORDER.reset(self._token)
            self._token = None
        self._parent = None

    def record(self, call: LLMCallRecord) -> None:
        """Add a single LLM call to this recorder and any parent recorder."""
        self._record_local(call)
        if self._parent is not None:
            self._parent.record(call)

    def _record_local(self, call: LLMCallRecord) -> None:
        self.calls.append(call)
        self.total_latency_ms += int(call.latency_ms or 0)
        self.usage += LLMUsage(
            input_tokens=int(call.input_tokens),
            output_tokens=int(call.output_tokens),
            cached_input_tokens=int(call.cached_input_tokens),
            cache_creation_input_tokens=int(call.cache_creation_input_tokens),
            reasoning_tokens=int(call.reasoning_tokens),
            llm_calls=1,
            input_excludes_cache=bool(call.input_excludes_cache),
        )
        if not self.primary_model and call.model_name:
            self.primary_model = call.model_name
        if not self.primary_provider and call.model_provider:
            self.primary_provider = call.model_provider

    def cost_usd(self, config: LLMCostConfig | None = None) -> float:
        """Return rolled-up cost, priced per call at that call's model."""
        if self.calls:
            return round(sum(_call_cost_usd(c, config) for c in self.calls), 6)
        if config is None:
            return 0.0
        return round(self.usage.cost_usd(config), 6)

    def to_audit_dict(self, config: LLMCostConfig | None = None) -> dict[str, Any]:
        """Return a dictionary shaped for the AuditEvent / Assessment writes."""
        return {
            "input_tokens": int(self.usage.input_tokens),
            "output_tokens": int(self.usage.output_tokens),
            "cached_input_tokens": int(self.usage.cached_input_tokens),
            "cache_creation_input_tokens": int(self.usage.cache_creation_input_tokens),
            "reasoning_tokens": int(self.usage.reasoning_tokens),
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


def _provider_excludes_cache(provider: str) -> bool:
    return provider.strip().lower() in ("aws", "bedrock")


def _default_tracking_callback(**kwargs: Any) -> None:
    """Forward LLM usage from invoke_llm_json into the active recorder.

    Mapped from ``track_llm_usage`` keyword arguments to a
    ``LLMCallRecord``. Cache reads and cache writes are kept separate so
    cost math can bill writes at the 1.25x write rate (Bedrock).
    """
    rec = _ACTIVE_RECORDER.get()
    if rec is None:
        return
    try:
        provider = str(kwargs.get("model_provider") or "")
        excludes = kwargs.get("input_excludes_cache")
        if excludes is None:
            excludes = _provider_excludes_cache(provider)
        rec.record(
            LLMCallRecord(
                agent_task=str(kwargs.get("agent_task") or ""),
                model_name=str(kwargs.get("model_name") or ""),
                model_provider=provider,
                input_tokens=int(kwargs.get("input_tokens") or 0),
                output_tokens=int(kwargs.get("output_tokens") or 0),
                cached_input_tokens=int(kwargs.get("cache_read_input_tokens") or 0),
                cache_creation_input_tokens=int(
                    kwargs.get("cache_creation_input_tokens") or 0
                ),
                reasoning_tokens=int(kwargs.get("reasoning_tokens") or 0),
                input_excludes_cache=bool(excludes),
                model_tier=str(kwargs.get("model_tier") or ""),
                latency_ms=int(kwargs.get("latency_ms") or 0),
                success=bool(kwargs.get("success", True)),
                error_message=str(kwargs.get("error_message") or ""),
                patient_id=str(kwargs.get("patient_id") or ""),
            )
        )
    except Exception:
        logger.debug("LLMUsageRecorder default callback failed", exc_info=True)


set_tracking_callback(_default_tracking_callback)
