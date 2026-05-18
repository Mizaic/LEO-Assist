"""Single-VT runner for jest and playwright UI tests.

Routes by framework:
  jest        -> npx jest --testPathPatterns "<pattern>" --no-coverage
  playwright  -> npx playwright test <spec_path>

Both are rooted in services/ui/. Captures stdout+stderr to the
structured log directory.

Usage:
    python -m scripts.vt_execution.run_jest_vt \\
        --vt VT-XXXXXXXX --framework jest \\
        --path services/ui/src/__tests__/foo.test.tsx
    python -m scripts.vt_execution.run_jest_vt \\
        --vt VT-XXXXXXXX --framework playwright \\
        --path services/ui/e2e/foo.spec.ts
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
UI_DIR = ROOT / "services" / "ui"
LOGS = ROOT / "scripts" / "vt_execution" / "logs"


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _log_path(vt_dcid: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    return LOGS / f"{vt_dcid}-{_utc()}.log"


def _jest_pattern(path: str) -> str:
    """Path relative to repo root -> jest --testPathPatterns regex.

    jest's testPathPatterns is a regex matched against the absolute
    path. We strip the services/ui/ prefix so that running from the
    UI dir yields a stable pattern.
    """
    rel = path
    if rel.startswith("services/ui/"):
        rel = rel[len("services/ui/"):]
    return rel.replace(".", "\\.")


def run_jest(vt_dcid: str, path: str) -> dict:
    pattern = _jest_pattern(path)
    cmd = ["npx", "jest", "--testPathPatterns", pattern,
           "--no-coverage", "--colors=false"]
    return _exec(vt_dcid, "jest", cmd, cwd=UI_DIR)


def run_playwright(vt_dcid: str, path: str) -> dict:
    rel = path
    if rel.startswith("services/ui/"):
        rel = rel[len("services/ui/"):]
    cmd = ["npx", "playwright", "test", rel, "--reporter=list"]
    return _exec(vt_dcid, "playwright", cmd, cwd=UI_DIR)


def _exec(vt_dcid: str, framework: str, cmd: list[str], cwd: Path) -> dict:
    log_file = _log_path(vt_dcid)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    env = dict(os.environ)
    env.setdefault("CI", "1")
    env.setdefault("FORCE_COLOR", "0")

    with log_file.open("w") as fh:
        fh.write(f"# vt={vt_dcid}\n# framework={framework}\n")
        fh.write(f"# started_at={started}\n# cwd={cwd}\n")
        fh.write(f"# cmd={' '.join(cmd)}\n\n")
        fh.flush()
        proc = subprocess.run(
            cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT,
            env=env, check=False,
        )
    finished = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "vt_dcid": vt_dcid,
        "framework": framework,
        "exit_code": proc.returncode,
        "result": "pass" if proc.returncode == 0 else "fail",
        "started_at": started,
        "finished_at": finished,
        "log_path": str(log_file.relative_to(ROOT)),
        "command": " ".join(cmd),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vt", required=True)
    p.add_argument("--framework", choices=["jest", "playwright"],
                   required=True)
    p.add_argument("--path", required=True)
    args = p.parse_args()

    target = ROOT / args.path
    if not target.exists():
        out = {
            "vt_dcid": args.vt,
            "framework": args.framework,
            "exit_code": 127,
            "result": "fail",
            "error": f"test file not on disk: {args.path}",
            "log_path": "",
        }
        print(json.dumps(out))
        return 1

    if args.framework == "jest":
        summary = run_jest(args.vt, args.path)
    else:
        summary = run_playwright(args.vt, args.path)
    print(json.dumps(summary))
    return 0 if summary["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
