"""Phase 13 probe - inspect a few Atlas DOs to see the source_reference shape."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import call_tool, initialize  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"


def main() -> int:
    initialize()
    print("== get_design_control_stats ==")
    stats = call_tool(
        "get_design_control_stats", {"product_id": PRODUCT_ID}
    )
    print(json.dumps(stats, indent=2)[:2000])
    print()
    print("== probe alt readers for source_reference ==")
    matrix = call_tool("get_traceability_matrix", {"product_id": PRODUCT_ID})
    raw_m = json.dumps(matrix, indent=2)
    print(f"matrix length: {len(raw_m)} bytes")
    for needle in ("source_reference", "sourceReference"):
        if needle in raw_m:
            idx = raw_m.find(needle)
            print(f"  matrix has '{needle}' at offset {idx}; ctx: "
                  f"{raw_m[max(0, idx - 30):idx + 200]!r}")
        else:
            print(f"  matrix has NO '{needle}'")
    print()
    search = call_tool(
        "search_design_controls",
        {
            "product_id": PRODUCT_ID,
            "query": "EpisodeOfCare status",
            "dc_type": "design-output",
            "limit": 3,
        },
    )
    raw_s = json.dumps(search, indent=2)
    print(f"search length: {len(raw_s)} bytes")
    for needle in ("source_reference", "sourceReference"):
        if needle in raw_s:
            print(f"  search has '{needle}'")
        else:
            print(f"  search has NO '{needle}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
