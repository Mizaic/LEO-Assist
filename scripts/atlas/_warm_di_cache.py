"""Warm the Atlas DI full-detail cache for all 262 design-input nodes.

Refetches anything currently stored as `_error`, and adds anything
missing.  Designed for resume-safety: repeat invocations are no-ops
on already-cached entries.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402

CACHE_PATH = REPO / "scripts" / "atlas" / ".phase2_atlas_full_cache.json"
ATLAS_MATRIX = (
    REPO / "design-controls" / "atlas-baseline-2026-04-19" / "traceability-matrix.json"
)


def main() -> int:
    matrix = json.loads(ATLAS_MATRIX.read_text())
    di_dc_ids = [n["dcId"] for n in matrix["nodes"] if n.get("dcType") == "design-input"]
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    print(f"Atlas DIs: {len(di_dc_ids)}; cached so far: {len(cache)}")

    mcp.initialize()
    targets = [
        d for d in di_dc_ids
        if d not in cache or (isinstance(cache.get(d), dict) and "_error" in cache[d])
    ]
    print(f"Need to fetch: {len(targets)}")
    for i, dc_id in enumerate(targets, start=1):
        try:
            res = mcp.call_tool(
                "get_design_control",
                {"dc_type": "design-input", "dc_id": dc_id},
            )
            inner = res.get("designInput") or res.get("design_input") or res
            cache[dc_id] = inner
            kind = "OK"
        except mcp.McpError as e:
            cache[dc_id] = {"_error": str(e)[:200]}
            kind = "ERR"
        if i % 5 == 0 or i == len(targets):
            CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))
        print(f"  [{i}/{len(targets)}] {dc_id} -> {kind}")
        time.sleep(0.05)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))
    ok = sum(1 for v in cache.values() if isinstance(v, dict) and "_error" not in v)
    err = sum(1 for v in cache.values() if isinstance(v, dict) and "_error" in v)
    print(f"\nFinal: cached={len(cache)} ok={ok} err={err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
