"""Resolve the guideline bitmap version stamped on Validation Lab runs.

Atlas:
  DI: DI-58CE9939
  DO: DO-3A70C3DD
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001").rstrip(
    "/"
)
_BITMAP_STATUS_TIMEOUT_S = 5.0


def resolve_ruleset_version(explicit: str | None = None) -> str | None:
    """Return the ruleset version to stamp on a Lab run.

    Prefer an explicit override (candidate pin). Otherwise resolve the
    live bitmap pointer from terminology status. Failures return None
    so Lab runs still enqueue.
    """
    pinned = str(explicit or "").strip()
    if pinned:
        return pinned
    try:
        url = (
            f"{TERMINOLOGY_API_URL}/terminology/guidelines/bitmap/status"
            "?scope_type=global&scope_id=default"
        )
        with httpx.Client(timeout=_BITMAP_STATUS_TIMEOUT_S) as client:
            resp = client.get(url)
        if not resp.is_success:
            return None
        active = (resp.json() or {}).get("active_version")
        return str(active).strip() or None if active else None
    except Exception:
        logger.warning(
            "validation_lab: could not resolve live bitmap version",
            exc_info=True,
        )
        return None
