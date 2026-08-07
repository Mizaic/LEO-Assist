"""Safe Service Bus runtime metadata for startup logs and health checks.

Atlas trace:
  DO: DO-2C7DDA31
  DI: DI-A3EF22B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C7DDA31")
"""

from __future__ import annotations

import logging
import os
from typing import Any


def connection_string_endpoint(connection_string: str) -> str | None:
    """Return the sb:// host from a connection string without secrets."""
    for part in connection_string.split(";"):
        part = part.strip()
        if part.startswith("Endpoint="):
            return part.split("=", 1)[1].strip().rstrip("/")
    return None


def normalize_service_bus_host(value: str | None) -> str | None:
    """Normalise namespace env or endpoint values to a comparable host."""
    if not value:
        return None
    host = value.strip().rstrip("/")
    for prefix in ("https://", "http://", "sb://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/") or None


def describe_message_bus_runtime(*, queue_name: str | None = None) -> dict[str, Any]:
    """Describe configured message bus settings without logging secrets."""
    namespace_env = normalize_service_bus_host(
        os.getenv("AZURE_SERVICE_BUS_NAMESPACE", "").strip() or None
    )
    connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "").strip()
    queue = queue_name or os.getenv("PIPELINE_QUEUE_NAME", "").strip() or None

    if not namespace_env and not connection_string:
        return {"mode": "in_memory", "queue": queue}

    auth = "connection_string" if connection_string else "managed_identity"
    endpoint = normalize_service_bus_host(connection_string_endpoint(connection_string))
    mismatch = bool(
        namespace_env and endpoint and namespace_env.lower() != endpoint.lower()
    )
    return {
        "mode": "azure",
        "auth": auth,
        "namespace_env": namespace_env,
        "endpoint": endpoint,
        "queue": queue,
        "namespace_endpoint_mismatch": mismatch,
    }


def log_message_bus_startup(
    logger: logging.Logger,
    *,
    service: str,
    queue_name: str | None = None,
) -> None:
    """Log which Service Bus namespace and queue this process will use."""
    info = describe_message_bus_runtime(queue_name=queue_name)
    if info.get("mode") == "in_memory":
        logger.info(
            "%s message bus configured: mode=in_memory queue=%s",
            service,
            info.get("queue") or "-",
        )
        return

    logger.info(
        "%s message bus configured: mode=azure auth=%s "
        "namespace_env=%s endpoint=%s queue=%s",
        service,
        info.get("auth"),
        info.get("namespace_env") or "-",
        info.get("endpoint") or "-",
        info.get("queue") or "-",
    )
    if info.get("namespace_endpoint_mismatch"):
        logger.warning(
            "%s message bus mismatch: AZURE_SERVICE_BUS_NAMESPACE=%s but "
            "connection string endpoint=%s",
            service,
            info.get("namespace_env"),
            info.get("endpoint"),
        )
