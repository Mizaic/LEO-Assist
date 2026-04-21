"""Atlas-side VT updater.

Records a verification run via the Atlas MCP `record_verification_run`
tool. The tool requires the **internal UUID** of the VT, not the dcId
(see scripts/atlas/PHASE3_NOTES.md bug #2).

The notes field cites the actual log path -- no synthetic entries
(quality gate from the brief).

Usage:
    python -m scripts.vt_execution.update_atlas_vt \\
        --vt-uuid <uuid> --vt-dcid VT-XXXXXXXX \\
        --result pass --log-path scripts/vt_execution/logs/X.log \\
        [--bug-ref BUG-123] [--executor name] [--environment local]

Returns 0 on success, prints the Atlas response on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.vt_execution._atlas import record_vt_run  # noqa: E402


def build_notes(log_path: str, bug_ref: str, extra: str) -> str:
    parts: list[str] = []
    if log_path:
        parts.append(f"log: {log_path}")
    if bug_ref:
        parts.append(f"bug: {bug_ref}")
    if extra:
        parts.append(extra)
    return " | ".join(parts) if parts else "automated run"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vt-uuid", required=True,
                   help="Internal UUID of the VT (NOT the dcId).")
    p.add_argument("--vt-dcid", default="",
                   help="VT dcId for log readability.")
    p.add_argument("--result", choices=["pass", "fail"], required=True)
    p.add_argument("--log-path", required=True,
                   help="Repo-relative path to the run log.")
    p.add_argument("--bug-ref", default="",
                   help="Required when result=fail and the failure "
                        "is a tracked regression.")
    p.add_argument("--executor", default="vt-execution-runner")
    p.add_argument("--environment", default="local")
    p.add_argument("--extra-notes", default="")
    args = p.parse_args()

    if not args.log_path:
        print("ERROR: --log-path is required (no synthetic entries)",
              file=sys.stderr)
        return 2
    log_full = ROOT / args.log_path
    if not log_full.exists():
        print(f"ERROR: log file does not exist: {args.log_path}",
              file=sys.stderr)
        return 2

    notes = build_notes(args.log_path, args.bug_ref, args.extra_notes)
    if args.vt_dcid:
        notes = f"[{args.vt_dcid}] {notes}"

    try:
        resp = record_vt_run(
            vt_uuid=args.vt_uuid,
            result=args.result,
            notes=notes,
            executed_by=args.executor,
            environment=args.environment,
        )
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "vt_uuid": args.vt_uuid,
            "vt_dcid": args.vt_dcid,
            "error": str(exc),
        }))
        return 1

    print(json.dumps({
        "ok": True,
        "vt_uuid": args.vt_uuid,
        "vt_dcid": args.vt_dcid,
        "result": args.result,
        "atlas_response": resp,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
