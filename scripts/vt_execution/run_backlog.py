"""Backlog orchestrator: read mvp_vt_backlog.csv, run unexecuted VTs.

For each row in the backlog where current_status != "passed":

  1. Pre-flight: skip if automation_status == manual (route to manual track),
     skip if framework is unknown (route to triage), skip if test file is
     not on disk (route to paper-vt track).
  2. Dispatch to the framework runner (pytest / jest / playwright).
  3. On pass: call update_atlas_vt to record the run, mark the row passed.
  4. On fail: leave row marked fail; the human triage step decides whether
     it is a real regression (open bug) or a stale-test bug (fix-and-rerun).
  5. After every 25 VTs, print a one-line summary and persist the CSV.

Usage:
    python -m scripts.vt_execution.run_backlog [--release R1] [--limit N]
                                               [--dry-run]
                                               [--smoke-test]
                                               [--update-atlas]

`--smoke-test` runs against rows where current_status == "passed" and does
NOT touch Atlas. Used to verify the runner pipeline end-to-end on day 1.

`--update-atlas` is the day-2+ default. Without it, runs execute but Atlas
is not touched (useful for debugging).

ASCII only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "scripts" / "vt_execution" / "mvp_vt_backlog.csv"
LOG_DIR = ROOT / "scripts" / "vt_execution" / "logs"

CSV_COLS = [
    "vt_dcid", "di_dcid", "un_dcid", "release",
    "framework", "automation_status",
    "test_file_path", "on_disk", "current_status",
    "owner", "run_started_at", "run_finished_at",
    "run_result", "run_log_path", "atlas_updated_at",
    "vt_uuid", "vt_title",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_backlog(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def save_backlog(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CSV_COLS})


def call_runner(row: dict) -> dict:
    """Invoke the framework runner and return its JSON summary dict."""
    fw = row["framework"]
    py = ".venv/bin/python"
    if fw == "pytest":
        cmd = [py, "-m", "scripts.vt_execution.run_pytest_vt",
               "--vt", row["vt_dcid"], "--path", row["test_file_path"]]
    elif fw in ("jest", "playwright"):
        cmd = [py, "-m", "scripts.vt_execution.run_jest_vt",
               "--vt", row["vt_dcid"], "--framework", fw,
               "--path", row["test_file_path"]]
    else:
        return {"vt_dcid": row["vt_dcid"], "framework": fw,
                "result": "fail", "error": f"unsupported framework: {fw}",
                "log_path": ""}
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False,
                          capture_output=True, text=True)
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return {"vt_dcid": row["vt_dcid"], "framework": fw,
                "result": "fail",
                "error": f"runner produced no output (rc={proc.returncode}): "
                         f"{proc.stderr[:300]}",
                "log_path": ""}
    try:
        return json.loads(out[-1])
    except json.JSONDecodeError:
        return {"vt_dcid": row["vt_dcid"], "framework": fw,
                "result": "fail",
                "error": f"runner JSON parse failed: {out[-1][:200]}",
                "log_path": ""}


def call_atlas_update(row: dict, summary: dict, bug_ref: str = "") -> dict:
    py = ".venv/bin/python"
    cmd = [py, "-m", "scripts.vt_execution.update_atlas_vt",
           "--vt-uuid", row["vt_uuid"], "--vt-dcid", row["vt_dcid"],
           "--result", summary["result"],
           "--log-path", summary.get("log_path", ""),
           "--executor", "vt-execution-runner",
           "--environment", "local"]
    if bug_ref:
        cmd.extend(["--bug-ref", bug_ref])
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False,
                          capture_output=True, text=True)
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return {"ok": False, "error": proc.stderr[:300]}
    try:
        return json.loads(out[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"parse failed: {out[-1][:200]}"}


def categorise(row: dict) -> str:
    """Return one of: ready, manual, paper, unknown_fw, already_passed."""
    if row.get("current_status") == "passed":
        return "already_passed"
    if row.get("automation_status") == "manual":
        return "manual"
    if row.get("on_disk") != "true":
        return "paper"
    if row.get("framework") not in ("pytest", "jest", "playwright"):
        return "unknown_fw"
    return "ready"


def apply_run_to_all_rows(all_rows: list[dict], vt_dcid: str,
                          summary: dict, atlas_status: str) -> None:
    """Propagate the run result to every CSV row for the same VT."""
    for r in all_rows:
        if r["vt_dcid"] != vt_dcid:
            continue
        r["run_started_at"] = summary.get("started_at", utc_now())
        r["run_finished_at"] = summary.get("finished_at", utc_now())
        r["run_result"] = summary.get("result", "fail")
        r["run_log_path"] = summary.get("log_path", "")
        r["current_status"] = atlas_status
        if atlas_status in ("passed",):
            r["atlas_updated_at"] = utc_now()


def execute_row(row: dict, all_rows: list[dict],
                update_atlas: bool, dry_run: bool) -> dict:
    """Run the test for `row`'s VT and propagate results across all rows
    that share the same vt_dcid. Returns the runner summary."""
    summary = call_runner(row)
    result = summary.get("result", "fail")

    if result == "pass":
        if update_atlas and not dry_run:
            atlas = call_atlas_update(row, summary)
            atlas_status = ("passed" if atlas.get("ok")
                            else "atlas_update_failed")
        else:
            atlas_status = "passed_local_only"
    elif result == "noop":
        atlas_status = "needs_test_path"
    else:
        atlas_status = "failed"

    apply_run_to_all_rows(all_rows, row["vt_dcid"], summary, atlas_status)
    return summary


def report_chunk(idx: int, results: dict[str, int]) -> None:
    print(
        f"  [{idx}] passed={results.get('pass', 0)} "
        f"failed={results.get('fail', 0)} "
        f"manual={results.get('manual', 0)} "
        f"paper={results.get('paper', 0)} "
        f"unknown_fw={results.get('unknown_fw', 0)} "
        f"already_passed={results.get('already_passed', 0)}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", default="",
                   help="Filter to one release tag (e.g. R1).")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap the number of executions (after filters).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--update-atlas", action="store_true",
                   help="Write results back to Atlas (default off).")
    p.add_argument("--smoke-test", action="store_true",
                   help="Target rows already marked passed; "
                        "verifies the runner end-to-end without "
                        "regressing real state.")
    args = p.parse_args()

    if not BACKLOG.exists():
        print(f"backlog not found: {BACKLOG}", file=sys.stderr)
        return 2

    rows = load_backlog(BACKLOG)
    print(f"loaded {len(rows)} backlog rows from {BACKLOG.name}")

    targets: list[dict] = []
    seen_vts: set[str] = set()
    for row in rows:
        if args.release and row.get("release") != args.release:
            continue
        if row["vt_dcid"] in seen_vts:
            continue
        if args.smoke_test:
            if row.get("current_status") != "passed":
                continue
            if row.get("automation_status") != "automated":
                continue
            if row.get("on_disk") != "true":
                continue
        else:
            if row.get("current_status") == "passed":
                continue
        targets.append(row)
        seen_vts.add(row["vt_dcid"])
        if args.limit and len(targets) >= args.limit:
            break
    print(f"selected {len(targets)} distinct VTs "
          f"(smoke_test={args.smoke_test}, release={args.release or 'ANY'})")

    counts: dict[str, int] = {}
    last_save = 0
    for i, row in enumerate(targets, 1):
        cat = categorise(row) if not args.smoke_test else "ready"
        if cat in ("manual", "paper", "unknown_fw"):
            counts[cat] = counts.get(cat, 0) + 1
            if not row.get("owner"):
                row["owner"] = f"track:{cat}"
            if i % 25 == 0:
                report_chunk(i, counts)
                save_backlog(BACKLOG, rows)
                last_save = i
            continue
        summary = execute_row(row, rows, update_atlas=args.update_atlas,
                              dry_run=args.dry_run)
        if args.smoke_test:
            apply_run_to_all_rows(rows, row["vt_dcid"], summary, "passed")
            counts[summary.get("result", "fail")] = counts.get(
                summary.get("result", "fail"), 0) + 1
        else:
            counts[summary.get("result", "fail")] = counts.get(
                summary.get("result", "fail"), 0) + 1
        print(f"  {i:4d}/{len(targets)} {row['vt_dcid']:14s} "
              f"{row['framework']:11s} {summary.get('result','?'):4s} "
              f"{row.get('test_file_path','')[:80]}")
        if i % 25 == 0:
            report_chunk(i, counts)
            save_backlog(BACKLOG, rows)
            last_save = i

    if last_save < len(targets):
        save_backlog(BACKLOG, rows)
    print("\n=== final tally ===")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
