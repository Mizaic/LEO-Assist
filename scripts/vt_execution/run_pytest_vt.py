"""Single-VT pytest runner.

Runs pytest against one test file path and writes the full
stdout+stderr to the structured log directory. Returns a JSON
summary on stdout, exits 0 if pytest exited 0, else 1.

Usage:
    python -m scripts.vt_execution.run_pytest_vt \\
        --vt VT-XXXXXXXX --path services/api/tests/test_foo.py \\
        [--node-id "::test_only"] [--marker fast]

The runner does NOT touch Atlas. The caller (run_backlog.py) is
responsible for routing the result to update_atlas_vt.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "scripts" / "vt_execution" / "logs"


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _log_path(vt_dcid: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    return LOGS / f"{vt_dcid}-{_utc()}.log"


def run(vt_dcid: str, path: str, node_id: str = "",
        marker: str = "") -> dict:
    target = path + node_id
    cmd = [".venv/bin/python", "-m", "pytest", target, "-v", "--tb=short",
           "--no-header", "-p", "no:cacheprovider"]
    if marker:
        cmd.extend(["-m", marker])

    log_file = _log_path(vt_dcid)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")

    with log_file.open("w") as fh:
        fh.write(f"# vt={vt_dcid}\n# started_at={started}\n")
        fh.write(f"# cmd={' '.join(cmd)}\n# cwd={ROOT}\n\n")
        fh.flush()
        proc = subprocess.run(
            cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
            env=env, check=False,
        )
    finished = dt.datetime.now(dt.timezone.utc).isoformat()

    rc = proc.returncode
    if rc == 0:
        result = "pass"
    elif rc == 5:
        result = "noop"
    else:
        result = "fail"

    return {
        "vt_dcid": vt_dcid,
        "framework": "pytest",
        "exit_code": rc,
        "result": result,
        "started_at": started,
        "finished_at": finished,
        "log_path": str(log_file.relative_to(ROOT)),
        "command": " ".join(cmd),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vt", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--node-id", default="")
    p.add_argument("--marker", default="")
    args = p.parse_args()

    target_path = ROOT / args.path
    if not target_path.exists():
        out = {
            "vt_dcid": args.vt,
            "framework": "pytest",
            "exit_code": 127,
            "result": "fail",
            "error": f"test file not on disk: {args.path}",
            "log_path": "",
        }
        print(json.dumps(out))
        return 1

    summary = run(args.vt, args.path, args.node_id, args.marker)
    print(json.dumps(summary))
    return 0 if summary["result"] == "pass" else 1 if summary["result"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
