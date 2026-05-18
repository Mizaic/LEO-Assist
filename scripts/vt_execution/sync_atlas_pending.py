"""Sync VTs that passed locally but failed Atlas update (Atlas outage).

Selects every backlog row whose current_status is "atlas_update_failed"
(plus any rows whose run_result is "pass" but atlas_updated_at is empty)
and re-calls Atlas record_verification_run with exponential backoff.

Use after an Atlas / QMS Graph API outage to drain the local sync
queue without re-running tests.

Usage:
    python -m scripts.vt_execution.sync_atlas_pending [--dry-run]
                                                      [--max-retries N]
                                                      [--initial-delay S]

ASCII only. Tooling, not under design control.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import time
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "scripts" / "vt_execution" / "mvp_vt_backlog.csv"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def needs_sync(row: dict) -> bool:
    if row.get("current_status") == "atlas_update_failed":
        return True
    if (row.get("run_result") == "pass"
            and not row.get("atlas_updated_at")
            and row.get("run_log_path")):
        return True
    return False


def call_atlas(row: dict) -> dict:
    cmd = [
        ".venv/bin/python", "-m", "scripts.vt_execution.update_atlas_vt",
        "--vt-uuid", row["vt_uuid"], "--vt-dcid", row["vt_dcid"],
        "--result", "pass", "--log-path", row["run_log_path"],
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False,
                          capture_output=True, text=True)
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return {"ok": False, "error": (proc.stderr or "")[:300]}
    try:
        return json.loads(out[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"parse failed: {out[-1][:200]}"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-retries", type=int, default=10)
    p.add_argument("--initial-delay", type=float, default=10.0)
    args = p.parse_args()

    rows = list(csv.DictReader(open(BACKLOG)))
    fields = list(rows[0].keys())
    pending: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        if r["vt_dcid"] in seen:
            continue
        if needs_sync(r):
            pending.append(r)
            seen.add(r["vt_dcid"])
    print(f"pending: {len(pending)} distinct VTs")

    if args.dry_run:
        for r in pending:
            print(f"  would sync {r['vt_dcid']} log={r['run_log_path']}")
        return 0

    synced: set[str] = set()
    delay = args.initial_delay
    for attempt in range(1, args.max_retries + 1):
        if not pending:
            break
        print(f"\n=== attempt {attempt}/{args.max_retries} "
              f"({len(pending)} remaining) ===")
        still: list[dict] = []
        for r in pending:
            resp = call_atlas(r)
            ok = resp.get("ok", False)
            print(f"  {r['vt_dcid']:14s} ok={ok}"
                  + ("" if ok else f"  err={str(resp.get('error',''))[:120]}"))
            if ok:
                synced.add(r["vt_dcid"])
            else:
                still.append(r)
        pending = still
        if pending and attempt < args.max_retries:
            print(f"  sleeping {delay:.0f}s before retry...")
            time.sleep(delay)
            delay = min(delay * 1.5, 120)

    if synced:
        for r in rows:
            if r["vt_dcid"] in synced:
                r["current_status"] = "passed"
                r["atlas_updated_at"] = utc_now()
        with open(BACKLOG, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    print(f"\nfinal: synced {len(synced)} of "
          f"{len(synced) + len(pending)} pending")
    if pending:
        print("still failing (Atlas may still be down):")
        for r in pending:
            print(f"  {r['vt_dcid']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
