"""Shared logging bootstrap for runtime services.

Atlas trace:
  DO: DO-89AF1CCE
  DI: DI-3717DFB0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-89AF1CCE")

Console-first logging for local operations with consistent fields across
APIs and workers. Optional ANSI colour by level for terminal sessions.
Keeps a clear migration path to structured export later.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import sys
from collections.abc import Iterator

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
_correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)

_DEFAULT_QUIET_LOGGERS: tuple[str, ...] = (
    "PyRuSH",
    "botocore",
    "botocore.credentials",
    "urllib3",
    "httpx",
    "sentence_transformers",
    "transformers",
    "azure.servicebus",
    "azure.servicebus._pyamqp",
    "azure.servicebus._pyamqp.aio",
    "azure.core.pipeline.policies.http_logging_policy",
    "uamqp",
)

_DEFAULT_ACCESS_SUPPRESS_PATHS: tuple[str, ...] = (
    "/health",
    "/training/coding-review/recheck/status",
    "/pipeline/classification-disagreements",
)

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[svc=%(service)s req=%(request_id)s corr=%(correlation_id)s] "
    "%(message)s"
)

# ANSI colours for levelname only (ASCII escapes; keep messages readable).
_LEVEL_COLOURS: dict[int, str] = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"
_DIM = "\033[2m"


class _ContextFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name
        record.request_id = _request_id_ctx.get()
        record.correlation_id = _correlation_id_ctx.get()
        return True


class _AccessNoiseFilter(logging.Filter):
    def __init__(self, suppress_paths: tuple[str, ...]) -> None:
        super().__init__()
        self._suppress_paths = tuple(p.lower() for p in suppress_paths if p)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        msg = record.getMessage().lower()
        return not any(path in msg for path in self._suppress_paths)


class ColourFormatter(logging.Formatter):
    """Format records with colour-coded level names for terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        colour = _LEVEL_COLOURS.get(record.levelno)
        if colour:
            record.levelname = f"{colour}{original_levelname}{_RESET}"
        try:
            rendered = super().format(record)
        finally:
            record.levelname = original_levelname
        stamp = getattr(record, "asctime", None)
        if colour and stamp:
            # Dim the timestamp so INFO/WARN/ERROR stand out.
            rendered = rendered.replace(stamp, f"{_DIM}{stamp}{_RESET}", 1)
        return rendered


def colour_enabled(*, stream: object | None = None) -> bool:
    """Return True when ANSI colour should be applied to console logs.

    Respects:
      - NO_COLOR (https://no-color.org/)
      - LOG_COLOR=auto|always|never (default auto)
      - FORCE_COLOR / CLICOLOR_FORCE truthy overrides auto when stream is a TTY
    """
    if os.getenv("NO_COLOR", "").strip():
        return False

    mode = os.getenv("LOG_COLOR", "auto").strip().lower()
    if mode in {"0", "false", "off", "never", "no"}:
        return False
    if mode in {"1", "true", "on", "always", "yes"}:
        return True

    # auto
    force = os.getenv("FORCE_COLOR", "") or os.getenv("CLICOLOR_FORCE", "")
    if force.strip() and force.strip() not in {"0", "false", "off"}:
        return True

    target = stream if stream is not None else sys.stderr
    return bool(getattr(target, "isatty", lambda: False)())


def configure_logging(
    *,
    service_name: str,
    quiet_loggers: tuple[str, ...] | None = None,
) -> None:
    """Configure process-wide logging for one runtime service."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    access_level_name = os.getenv("ACCESS_LOG_LEVEL", "INFO").upper()
    access_level = getattr(logging, access_level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        force=True,
    )

    root = logging.getLogger()
    use_colour = colour_enabled(stream=sys.stderr)
    formatter: logging.Formatter
    if use_colour:
        formatter = ColourFormatter(_LOG_FORMAT)
    else:
        formatter = logging.Formatter(_LOG_FORMAT)

    context_filter = _ContextFilter(service_name)
    for handler in root.handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)

    suppress_paths_env = os.getenv("ACCESS_LOG_SUPPRESS_PATHS", "")
    if suppress_paths_env.strip():
        suppress_paths = tuple(
            p.strip() for p in suppress_paths_env.split(",") if p.strip()
        )
    else:
        suppress_paths = _DEFAULT_ACCESS_SUPPRESS_PATHS
    access_noise_filter = _AccessNoiseFilter(suppress_paths=suppress_paths)
    for handler in root.handlers:
        handler.addFilter(access_noise_filter)

    # Keep service loggers at the configured floor so info/warn/error all emit.
    logging.getLogger().setLevel(level)
    logging.getLogger(service_name).setLevel(level)
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(access_level)

    for name in quiet_loggers or _DEFAULT_QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.ERROR)
    logging.getLogger("neo4j.notifications").setLevel(logging.CRITICAL)


@contextlib.contextmanager
def logging_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> Iterator[None]:
    """Temporarily bind request/correlation IDs to all log records."""
    tokens: list[tuple[contextvars.ContextVar[str], contextvars.Token[str]]] = []
    try:
        if request_id:
            tokens.append((_request_id_ctx, _request_id_ctx.set(request_id)))
        if correlation_id:
            tokens.append(
                (_correlation_id_ctx, _correlation_id_ctx.set(correlation_id))
            )
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
