"""Phase 3b -- Add VT -> DO TESTS links by inverting DO -> VT traceability.

Most local VT YAMLs do not list `traceability.design_outputs`; instead each
local DO YAML declares `traceability.verification_tests: [VT-LEO-AI-...]`
(or, in the alternate schema, `verified_by: [...]`).

This script:

  1. Walks every local DO YAML and builds local_vt -> [local_do, ...].
  2. Resolves each local_vt to its Atlas dcId via atlas-id-mapping.csv
     (covers both the remap-recorded rows and the create rows from
     phase 3a/3b).
  3. Resolves each local_do to its Atlas dcId via the same CSV.
  4. Calls link_design_controls TESTS source_ids=[VT_dcId]
     target_ids=[DO_dcIds] for every (vt, [dos]) pair.

Outputs:
  - design-controls/phase9-vt-do-links.csv
  - scripts/atlas/.phase3b_vt_do_state.json (idempotent)

Usage:
  python3 scripts/atlas/phase3b_vt_do_link.py            # dry-run
  python3 scripts/atlas/phase3b_vt_do_link.py --live     # create links
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
DO_DIR = REPO / "design-controls" / "design-outputs"
MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
LEDGER_CSV = REPO / "design-controls" / "phase9-vt-do-links.csv"
STATE_PATH = REPO / "scripts" / "atlas" / ".phase3b_vt_do_state.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_id_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def build_inverse_map() -> dict[str, list[str]]:
    """Return local VT-LEO-AI-* -> [local DO-LEO-AI-*, ...]."""
    out: dict[str, list[str]] = {}
    for path in sorted(DO_DIR.glob("DO-LEO-AI-*.yaml")):
        try:
            docs = list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if not doc:
                continue
            items = doc if isinstance(doc, list) else [doc]
            for item in items:
                if not isinstance(item, dict):
                    continue
                local_do = item.get("id")
                if not (local_do and local_do.startswith("DO-LEO-AI-")):
                    continue
                vts: list[str] = []
                vts += _coerce_id_list(
                    ((item.get("traceability") or {}).get("verification_tests"))
                )
                vts += _coerce_id_list(item.get("verified_by"))
                seen: set[str] = set()
                for vt in vts:
                    if not vt or vt in seen:
                        continue
                    seen.add(vt)
                    out.setdefault(vt, []).append(local_do)
    return out


def load_mapping() -> tuple[dict[str, str], dict[str, str]]:
    """Return (do_local -> atlas_dc, vt_local -> atlas_dc)."""
    do_map: dict[str, str] = {}
    vt_map: dict[str, str] = {}
    with MAPPING_CSV.open() as f:
        for row in csv.DictReader(f):
            t = row.get("artefact_type")
            local = row.get("local_id") or ""
            atlas = row.get("atlas_id") or ""
            if not (local and atlas):
                continue
            if t == "DO":
                do_map[local] = atlas
            elif t == "VT":
                vt_map[local] = atlas
    return do_map, vt_map


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"started_at": None, "linked": {}}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--filter", type=str, default="")
    args = parser.parse_args()

    inverse = build_inverse_map()
    do_map, vt_map = load_mapping()
    print(
        f"Inverse map: {len(inverse)} VTs reference at least one local DO. "
        f"DOs in CSV: {len(do_map)}, VTs in CSV: {len(vt_map)}"
    )

    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    rows: list[dict[str, Any]] = []
    items = sorted(inverse.items())
    for idx, (local_vt, local_dos) in enumerate(items, start=1):
        if args.filter and local_vt != args.filter:
            continue
        atlas_vt = vt_map.get(local_vt)
        atlas_dos = sorted({
            do_map[do] for do in local_dos if do in do_map
        })
        out_row: dict[str, Any] = {
            "local_vt": local_vt,
            "atlas_vt": atlas_vt or "",
            "local_dos": ";".join(local_dos),
            "atlas_dos": ";".join(atlas_dos),
            "result": "",
            "error": "",
        }
        if not atlas_vt:
            out_row["result"] = "skip: VT not in mapping CSV"
            rows.append(out_row)
            continue
        if not atlas_dos:
            out_row["result"] = "skip: no parent DOs resolved"
            rows.append(out_row)
            continue
        cache_key = f"{atlas_vt}->{','.join(atlas_dos)}"
        if cache_key in state["linked"]:
            out_row["result"] = "cached: already linked"
            rows.append(out_row)
            continue
        if not args.live:
            out_row["result"] = f"dry-run: would link to {len(atlas_dos)} DO(s)"
            rows.append(out_row)
            print(
                f"  [{idx}/{len(items)}] {local_vt} -> {atlas_vt}: "
                f"{out_row['result']}"
            )
            continue
        try:
            mcp.call_tool(
                "link_design_controls",
                {
                    "source_ids": [atlas_vt],
                    "target_ids": atlas_dos,
                    "relationship": "TESTS",
                },
            )
            out_row["result"] = f"linked to {len(atlas_dos)} DO(s)"
            state["linked"][cache_key] = {"at": _now_iso()}
            save_state(state)
        except mcp.McpError as e:
            out_row["result"] = "link_error"
            out_row["error"] = str(e)[:300]
        print(
            f"  [{idx}/{len(items)}] {local_vt} -> {atlas_vt}: "
            f"{out_row['result']}"
        )
        rows.append(out_row)
        time.sleep(0.05)

    fields = ["local_vt", "atlas_vt", "local_dos", "atlas_dos", "result", "error"]
    with LEDGER_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"Wrote ledger: {LEDGER_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
