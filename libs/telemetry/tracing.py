"""OpenTelemetry tracing setup for the clinical pipeline.

Instruments each subgraph execution as a span. Traces the full path:
event received -> PlanDefinition evaluated -> subgraph dispatched -> Neo4j written.

The existing AuditEvent system (Neo4j) handles regulatory compliance logging.
OTEL handles development/debugging observability.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_tracer = None


def get_tracer():
    """Return the global OTEL tracer, initializing on first call."""
    global _tracer
    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "leo-pipeline"),
            "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
        })

        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("leo.pipeline")
    except ImportError:
        logger.debug("OpenTelemetry not installed — tracing disabled")
        _tracer = _NoopTracer()

    return _tracer


class _NoopSpan:
    """Fallback span when OTEL is not available."""
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def set_attribute(self, key: str, value: Any) -> None: pass
    def set_status(self, *args: Any) -> None: pass
    def add_event(self, name: str, attributes: dict | None = None) -> None: pass


class _NoopTracer:
    """Fallback tracer when OTEL is not available."""
    def start_as_current_span(self, name: str, **kwargs):
        return _NoopSpan()


def trace_subgraph(subgraph_id: str, patient_id: str = "", **attributes: Any):
    """Start a tracing span for a subgraph execution."""
    tracer = get_tracer()
    span = tracer.start_as_current_span(
        f"subgraph.{subgraph_id}",
        attributes={
            "subgraph.id": subgraph_id,
            "patient.id": patient_id,
            **{f"pipeline.{k}": str(v) for k, v in attributes.items()},
        },
    )
    return span
