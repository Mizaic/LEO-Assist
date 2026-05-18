"""Phase 14c -- resolve the 8 post-snapshot allow-list files.

All 8 files implement DO-313A49AE ("Admin portal Entra extension:
graph_client, /admin/entra router, schema source-tag, and capability-driven
UI"), which has parent DIs DI-31F4C232, DI-5A18A227, DI-6CF7FCE0.

Steps:
  1. update_design_output(DO-313A49AE) with a source_reference that lists
     the 8 file paths plus a [phase14c] tag.
  2. Refresh phase13c-atlas-cache.json for DO-313A49AE and its parent DIs.
  3. Insert audit rows for the 8 files into phase13a-file-trace-audit.csv.
  4. Re-run the stamper to write headers.
  5. Empty the manual allow-list (keep header + a comment row).
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
ALLOW_LIST = EVIDENCE / "phase13c-allow-list.csv"
AUDIT = EVIDENCE / "phase13a-file-trace-audit.csv"
CACHE = EVIDENCE / "phase13c-atlas-cache.json"
LEDGER = EVIDENCE / "phase14c-ledger.csv"

DO_ID = "DO-313A49AE"
PRIMARY_DI = "DI-31F4C232"  # the "what shall happen" DI
ADDITIONAL_DIS = ["DI-5A18A227", "DI-6CF7FCE0"]
PHASE14C_TAG = "[phase14c]"
MAX_FIELD = 4000

FILES = [
    "libs/graph_client/client.py",
    "libs/graph_client/errors.py",
    "libs/graph_client/obo.py",
    "services/api/app/routers/admin_entra.py",
    "services/ui/src/components/tenant/BindGroupDialog.tsx",
    "services/ui/src/components/tenant/EntraGroupPicker.tsx",
    "services/ui/src/components/tenant/EntraIntegration.tsx",
    "services/ui/src/components/tenant/EntraUserPicker.tsx",
]


def append_ledger(operation: str, subject: str, result: str, note: str) -> None:
    cols = ["operation", "subject", "result", "note"]
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow({"operation": operation, "subject": subject,
                    "result": result, "note": note})


def already_done(operation: str, subject: str) -> bool:
    if not LEDGER.exists():
        return False
    return any(
        r["operation"] == operation
        and r["subject"] == subject
        and r["result"] in ("ok", "skipped")
        for r in csv.DictReader(LEDGER.open())
    )


def step_update_do_source_reference() -> None:
    if already_done("update_design_output", DO_ID):
        print(f"  skip: {DO_ID} source_reference already updated this run")
        return
    initialize()
    print(f"Fetching current source_reference for {DO_ID}...")
    out = call_tool("get_design_control",
                    {"dc_id": DO_ID, "dc_type": "design-output"})
    do = out.get("designOutput", {}) or {}
    current = (do.get("source_reference") or "").strip()
    current_paths = []
    if current:
        for tag in (PHASE14C_TAG, "[phase13b]"):
            current = current.replace(tag, "")
        current_paths = [p.strip() for p in current.split(";") if p.strip()]
    merged = sorted(set(current_paths) | set(FILES))
    body = "; ".join(merged)
    tag = f" {PHASE14C_TAG}"
    if len(body) + len(tag) > MAX_FIELD:
        body = body[: MAX_FIELD - len(tag) - 4] + "..."
    new_value = body + tag
    print(f"  -> setting source_reference to {len(merged)} paths "
          f"({len(new_value)} chars)")
    out = call_tool("update_design_output",
                    {"dc_id": DO_ID, "source_reference": new_value})
    err = (out or {}).get("error")
    if err:
        append_ledger("update_design_output", DO_ID, "error", str(err)[:300])
        raise SystemExit(f"update_design_output failed: {err}")
    append_ledger("update_design_output", DO_ID, "ok",
                  f"source_reference set ({len(merged)} paths)")


def step_refresh_cache() -> None:
    print("Refreshing cache for DO and parent DIs...")
    cache = json.loads(CACHE.read_text())
    initialize()

    def fetch(dc_type, dcid):
        try:
            o = call_tool("get_design_control",
                          {"dc_id": dcid, "dc_type": dc_type})
        except McpError as e:
            print(f"  ! {dcid} ({dc_type}): {e}")
            return None
        trace = o.get("traceability", {}) or {}
        rec = {"dcId": dcid, "title": "", "design_inputs": [],
               "design_outputs": [], "risks": []}
        if dc_type == "design-output":
            rec["title"] = (o.get("designOutput") or {}).get("title", "")
        else:
            rec["title"] = (o.get("designInput") or {}).get("title", "")
        for di in trace.get("designInputs", []) or []:
            d = di.get("dcId") or di.get("dc_id")
            if d:
                rec["design_inputs"].append(d)
        for do in trace.get("designOutputs", []) or []:
            d = do.get("dcId") or do.get("dc_id")
            if d:
                rec["design_outputs"].append(d)
        for r in trace.get("risks", []) or []:
            d = r.get("dcId") or r.get("dc_id")
            if d:
                rec["risks"].append(d)
        return rec

    rec = fetch("design-output", DO_ID)
    if rec:
        cache["design_outputs"][DO_ID] = rec
        print(f"  cached {DO_ID}: design_inputs={rec['design_inputs']}")
    for di in [PRIMARY_DI] + ADDITIONAL_DIS:
        rec = fetch("design-input", di)
        if rec:
            cache["design_inputs"][di] = rec
            print(f"  cached {di}")
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    append_ledger("refresh_cache", "DO+DIs", "ok",
                  f"refreshed {DO_ID} and 3 parent DIs")


def step_insert_audit_rows() -> None:
    print("Inserting audit rows for the 8 files...")
    rows = list(csv.DictReader(AUDIT.open()))
    paths_in_audit = {r["path"] for r in rows}
    cols = list(rows[0].keys())
    n_added = 0
    for path in FILES:
        if path in paths_in_audit:
            continue
        new_row = {c: "" for c in cols}
        new_row["path"] = path
        new_row["header_state"] = "atlas"  # they will have headers after stamper
        new_row["owning_atlas_dos"] = DO_ID
        new_row["phase8_bucket_dir"] = "phase14c"
        rows.append(new_row)
        n_added += 1
    rows.sort(key=lambda r: r["path"])
    with AUDIT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  inserted {n_added} new audit rows")
    append_ledger("insert_audit_rows", "8 files", "ok",
                  f"added {n_added} rows")


def step_clear_allow_list() -> None:
    print("Clearing manual allow-list (header only)...")
    ALLOW_LIST.write_text(
        "path,reason,added_at,added_by\n"
    )
    append_ledger("clear_allow_list", "phase13c-allow-list.csv", "ok",
                  "all 8 rows resolved by phase14c")


def main() -> int:
    step_update_do_source_reference()
    step_refresh_cache()
    step_insert_audit_rows()
    step_clear_allow_list()
    print("\nDone. Next: re-run scripts/atlas/phase13c_stamp_headers.py "
          "--apply to write headers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
