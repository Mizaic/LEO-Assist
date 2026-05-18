"""Phase 14d-iii -- inject audit rows + cache + re-stamp.

Reads phase14d-bucket-ids.json and turns the bucket -> {un, di, do,
files} mapping into:

  1. New rows in phase13a-file-trace-audit.csv for every bucketed file
     (path, owning_atlas_dos = the new DO).
  2. Cache entries in phase13c-atlas-cache.json so the stamper resolves
     each new DO -> its parent DI without an extra Atlas fetch.

Then the caller can re-run scripts/atlas/phase13c_stamp_headers.py
--apply.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
AUDIT = EVIDENCE / "phase13a-file-trace-audit.csv"
CACHE = EVIDENCE / "phase13c-atlas-cache.json"
BUCKET_IDS = EVIDENCE / "phase14d-bucket-ids.json"


def main() -> int:
    ids = json.loads(BUCKET_IDS.read_text())

    # ----- Update audit -----
    rows = list(csv.DictReader(AUDIT.open()))
    cols = list(rows[0].keys())
    by_path = {r["path"]: r for r in rows}
    n_added = 0
    n_updated = 0
    for bucket_id, v in ids.items():
        do_id = v["do"]
        if not do_id.startswith("DO-"):
            do_id = "DO-" + do_id  # special bucket stores raw dcid suffix
        for path in v["files"]:
            if path in by_path:
                r = by_path[path]
                if not r.get("owning_atlas_dos"):
                    r["owning_atlas_dos"] = do_id
                    r["phase8_bucket_dir"] = f"phase14d:{bucket_id}"
                    n_updated += 1
            else:
                new_row = {c: "" for c in cols}
                new_row["path"] = path
                new_row["header_state"] = "atlas"
                new_row["owning_atlas_dos"] = do_id
                new_row["phase8_bucket_dir"] = f"phase14d:{bucket_id}"
                rows.append(new_row)
                by_path[path] = new_row
                n_added += 1
    rows.sort(key=lambda r: r["path"])
    with AUDIT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"audit: added {n_added} rows, updated {n_updated} rows")

    # ----- Update cache (synthetic: we know UN->DI->DO from Atlas writes) -----
    cache = json.loads(CACHE.read_text())
    n_do = 0
    n_di = 0
    for bucket_id, v in ids.items():
        do_id = v["do"]
        if not do_id.startswith("DO-"):
            do_id = "DO-" + do_id
        di_id = v["di"]
        additional = v.get("additional_dis", []) or []
        all_dis = ([di_id] if di_id else []) + list(additional)
        cache["design_outputs"][do_id] = {
            "dcId": do_id,
            "title": "phase14d bucket DO",
            "design_inputs": all_dis,
            "design_outputs": [],
            "risks": [],
        }
        n_do += 1
        for d in all_dis:
            if d and d not in cache["design_inputs"]:
                cache["design_inputs"][d] = {
                    "dcId": d,
                    "title": "phase14d bucket DI",
                    "design_inputs": [],
                    "design_outputs": [do_id],
                    "risks": [],
                }
                n_di += 1
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    print(f"cache: wrote {n_do} DOs, {n_di} new DIs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
