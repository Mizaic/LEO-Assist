"""Phase 13c pre-pass -- cache DO and DI traceability from Atlas.

For every unique DO in `phase13a-file-trace-audit.csv`, fetch
`get_design_control(dc_type="design-output", dc_id=...)` and persist:

  - parent design inputs (dcId list)
  - linked risks (dcId list)
  - title

For every unique DI cited in DI-only audit rows, fetch
`get_design_control(dc_type="design-input", dc_id=...)` and persist:

  - child design outputs (dcId list)
  - linked risks (dcId list)
  - title

Output: compliance/atlas-migration-evidence/phase13c-atlas-cache.json

Idempotent: re-running re-uses cached entries; only fetches the deltas.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import McpError, call_tool, initialize  # noqa: E402

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
AUDIT_CSV = EVIDENCE / "phase13a-file-trace-audit.csv"
CACHE_JSON = EVIDENCE / "phase13c-atlas-cache.json"


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def collect_targets() -> tuple[set[str], set[str]]:
    """Some Phase 13a rows put DO ids into the DI column (legacy DI mapped
    to an Atlas DO). Route every id to the correct fetcher by prefix."""
    audit = list(csv.DictReader(AUDIT_CSV.open()))
    dos: set[str] = set()
    dis: set[str] = set()
    for r in audit:
        for d in _split(r["owning_atlas_dos"]):
            if d.startswith("DO-"):
                dos.add(d)
            elif d.startswith("DI-"):
                dis.add(d)
        for d in _split(r["owning_atlas_dis"]):
            if d.startswith("DI-"):
                dis.add(d)
            elif d.startswith("DO-"):
                dos.add(d)
    return dos, dis


def load_cache() -> dict:
    if not CACHE_JSON.exists():
        return {"design_outputs": {}, "design_inputs": {}}
    return json.loads(CACHE_JSON.read_text())


def save_cache(cache: dict) -> None:
    CACHE_JSON.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def fetch_one(dc_type: str, dc_id: str) -> dict | None:
    try:
        out = call_tool(
            "get_design_control", {"dc_id": dc_id, "dc_type": dc_type}
        )
    except McpError as e:
        print(f"  ! {dc_id} ({dc_type}): {e}")
        return None
    trace = out.get("traceability", {}) or {}
    record = {
        "dcId": dc_id,
        "title": "",
        "design_inputs": [],
        "design_outputs": [],
        "risks": [],
    }
    if dc_type == "design-output":
        do = out.get("designOutput", {}) or {}
        record["title"] = do.get("title", "")
    else:
        di = out.get("designInput", {}) or {}
        record["title"] = di.get("title", "") or di.get("requirement", "")[:200]
    for di in trace.get("designInputs", []) or []:
        d = di.get("dcId") or di.get("dc_id")
        if d:
            record["design_inputs"].append(d)
    for do in trace.get("designOutputs", []) or []:
        d = do.get("dcId") or do.get("dc_id")
        if d:
            record["design_outputs"].append(d)
    for risk in trace.get("risks", []) or []:
        d = risk.get("dcId") or risk.get("dc_id")
        if d:
            record["risks"].append(d)
    return record


def main() -> int:
    print("Phase 13c pre-pass -- caching Atlas DI/DO traceability")
    initialize()

    dos, dis = collect_targets()
    print(f"  -> {len(dos)} unique DOs, {len(dis)} unique DIs to ensure cached")

    cache = load_cache()
    cached_dos = set(cache["design_outputs"])
    cached_dis = set(cache["design_inputs"])
    todo_dos = sorted(dos - cached_dos)
    todo_dis = sorted(dis - cached_dis)
    print(
        f"  -> already cached: {len(cached_dos)} DOs, {len(cached_dis)} DIs"
    )
    print(f"  -> to fetch: {len(todo_dos)} DOs, {len(todo_dis)} DIs")

    n_done = 0
    save_every = 10
    for d in todo_dos:
        rec = fetch_one("design-output", d)
        if rec is not None:
            cache["design_outputs"][d] = rec
        n_done += 1
        if n_done % save_every == 0:
            save_cache(cache)
            print(f"  ... cached {n_done}/{len(todo_dos) + len(todo_dis)} "
                  f"(last: {d})")
    for d in todo_dis:
        rec = fetch_one("design-input", d)
        if rec is not None:
            cache["design_inputs"][d] = rec
        n_done += 1
        if n_done % save_every == 0:
            save_cache(cache)
            print(f"  ... cached {n_done}/{len(todo_dos) + len(todo_dis)} "
                  f"(last: {d})")

    save_cache(cache)
    print(
        f"Done. cache has {len(cache['design_outputs'])} DOs, "
        f"{len(cache['design_inputs'])} DIs at {CACHE_JSON}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
