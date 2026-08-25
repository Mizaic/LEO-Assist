"""Re-run every automated on-disk VT and record to Atlas REST."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def load_env(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        k, v = t.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(str(ROOT / "services/ui/.env.local"))
load_env(str(ROOT / ".env"))
val = os.environ.get("ATLAS_VALIDATION_RUNS_BASE_URL", "").rstrip("/")
if val and not os.environ.get("ATLAS_VERIFICATION_RUNS_BASE_URL"):
    os.environ["ATLAS_VERIFICATION_RUNS_BASE_URL"] = (
        val[: -len("validation-runs")] + "verification-runs"
        if val.endswith("validation-runs")
        else val.replace("validation-runs", "verification-runs")
    )

from scripts.vt_execution.run_backlog import (  # noqa: E402
    BACKLOG,
    execute_row,
    load_backlog,
    save_backlog,
)

def main() -> int:
    rows = load_backlog(BACKLOG)
    seen: set[str] = set()
    targets = []
    for row in rows:
        if row["vt_dcid"] in seen:
            continue
        if row.get("automation_status") != "automated":
            continue
        if row.get("on_disk") != "true":
            continue
        if row.get("framework") not in ("pytest", "jest", "playwright"):
            continue
        targets.append(row)
        seen.add(row["vt_dcid"])
    print(f"rerun_targets={len(targets)}", flush=True)
    for i, row in enumerate(targets, 1):
        summary = execute_row(row, rows, update_atlas=True, dry_run=False)
        print(
            f"{i}/{len(targets)} {row['vt_dcid']} {row['framework']} "
            f"{summary.get('result', '?')} {row.get('test_file_path', '')}",
            flush=True,
        )
        if i % 10 == 0:
            save_backlog(BACKLOG, rows)
    save_backlog(BACKLOG, rows)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
