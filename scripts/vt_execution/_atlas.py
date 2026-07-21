"""Thin wrapper around the Atlas MCP transport for VT execution scripts.

Reuses the proven transport from scripts/atlas/_mcp_transport.py so we
inherit the SSE parsing, cookie / session handling, and retry behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.atlas._mcp_transport import call_tool, initialize  # noqa: E402
from scripts.atlas.product import PRODUCT_ID  # noqa: E402

_INITIALISED = False


def ensure_session() -> None:
    """Idempotent MCP session initialiser."""
    global _INITIALISED
    if _INITIALISED:
        return
    initialize()
    _INITIALISED = True


def get_dc(dc_type: str, dc_id: str) -> dict:
    """Fetch a single design control with full traceability."""
    ensure_session()
    return call_tool(
        "get_design_control",
        {"dc_type": dc_type, "dc_id": dc_id},
    )


def search_dc(query: str, dc_type: str, limit: int = 50) -> list[dict]:
    """Hybrid search; returns the result list (possibly empty)."""
    ensure_session()
    out = call_tool(
        "search_design_controls",
        {
            "query": query,
            "dc_type": dc_type,
            "product_id": PRODUCT_ID,
            "limit": limit,
        },
    )
    return out.get("result", []) if isinstance(out, dict) else []


def record_vt_run(
    vt_uuid: str,
    result: str,
    notes: str,
    executed_by: str,
    environment: str = "local",
) -> dict:
    """Record a verification test run.

    NOTE: vt_uuid MUST be the internal UUID, not the dcId. Phase 3
    found this the hard way (PHASE3_NOTES.md, bug #2).
    """
    ensure_session()
    return call_tool(
        "record_verification_run",
        {
            "vt_id": vt_uuid,
            "result": result,
            "notes": notes,
            "executed_by": executed_by,
            "environment": environment,
        },
    )
