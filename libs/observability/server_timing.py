"""Server-Timing middleware for FastAPI / Starlette.

Adds a `Server-Timing` response header so clients (and the browser
DevTools network panel) can attribute time to the backend handler.
This makes Phase 6 perf regressions obvious without needing to read
APM dashboards or backend logs.

Example output::

    Server-Timing: app;dur=312.4

The middleware is intentionally lightweight: it measures wall-clock
time in `time.perf_counter()` around the downstream handler and
appends a single `app` metric. Callers can extend the header with
finer-grained sub-timings (e.g. `neo4j;dur=...`) by writing to
`request.state.server_timings` from inside their own middlewares
or endpoints; this middleware will merge those values into the
final header.
"""

from __future__ import annotations

import time
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _format_metric(name: str, dur_ms: float) -> str:
    return f"{name};dur={dur_ms:.1f}"


class ServerTimingMiddleware(BaseHTTPMiddleware):
    """Append a Server-Timing header to every response.

    Other middlewares / endpoints can record extra metrics by
    appending `(name, duration_ms)` tuples to the
    `request.state.server_timings` list. The middleware initialises
    the list before delegating downstream so callers can rely on it
    always being present.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.server_timings = []
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        extras: Iterable = getattr(request.state, "server_timings", []) or []
        parts = [_format_metric("app", elapsed_ms)]
        for entry in extras:
            try:
                name, dur_ms = entry
            except (TypeError, ValueError):
                continue
            parts.append(_format_metric(str(name), float(dur_ms)))

        existing = response.headers.get("Server-Timing")
        if existing:
            response.headers["Server-Timing"] = f"{existing}, {', '.join(parts)}"
        else:
            response.headers["Server-Timing"] = ", ".join(parts)
        return response
