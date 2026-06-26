"""Atlas-side VT updater.

Records a verification run and optionally uploads the test log as evidence.

Preferred path: REST API via VerificationRunClient when
ATLAS_VERIFICATION_RUNS_BASE_URL is set. Supports screenshot/log upload.

Fallback: Atlas MCP `record_verification_run` tool (no evidence upload).

The VT UUID is the **internal UUID**, not the dcId.
See scripts/atlas/PHASE3_NOTES.md bug #2.

The log path is required -- no synthetic entries (quality gate).

Usage:
    python -m scripts.vt_execution.update_atlas_vt \\
        --vt-uuid <uuid> --vt-dcid VT-XXXXXXXX \\
        --result pass --log-path scripts/vt_execution/logs/X.log \\
        [--bug-ref BUG-123] [--executor name] [--environment local]

Returns 0 on success, prints JSON summary on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.vt_execution._atlas import record_vt_run  # noqa: E402
from scripts.vt_execution.atlas_verification_runs_rest import (  # noqa: E402
    VerificationRunClient,
    VerificationRunsNotConfigured,
    is_configured,
)


def build_notes(log_path: str, bug_ref: str, extra: str) -> str:
    parts: list[str] = []
    if log_path:
        parts.append(f"log: {log_path}")
    if bug_ref:
        parts.append(f"bug: {bug_ref}")
    if extra:
        parts.append(extra)
    return " | ".join(parts) if parts else "automated run"


def _record_via_rest(
    vt_uuid: str,
    vt_dcid: str,
    result: str,
    notes: str,
    log_full: Path,
    executor: str,
    environment: str,
) -> dict:
    """Record via REST API and upload the log as text/plain evidence."""
    client = VerificationRunClient.from_env()
    client.environment = environment
    run_id = client.create_run(vt_id=vt_uuid, executor=executor)
    log_bytes = log_full.read_bytes()
    client.record_step(run_id, 0, notes, result)
    client.upload_evidence(
        run_id, 0, log_bytes,
        caption=f"Test log for {vt_dcid or vt_uuid}",
        file_name=log_full.name,
        content_type="text/plain",
    )
    client.complete(
        run_id,
        result,
        summary=notes[:200] if result == "pass" else None,
        failure_reason=notes[:500] if result == "fail" else None,
    )
    return {"run_id": run_id, "method": "rest"}


def _record_via_mcp(
    vt_uuid: str,
    notes: str,
    result: str,
    executor: str,
    environment: str,
) -> dict:
    resp = record_vt_run(
        vt_uuid=vt_uuid,
        result=result,
        notes=notes,
        executed_by=executor,
        environment=environment,
    )
    return dict(resp or {}) | {"method": "mcp"}


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
                   help="Required when result=fail.")
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
        print(f"ERROR: log file not on disk: {args.log_path}",
              file=sys.stderr)
        return 2

    notes = build_notes(args.log_path, args.bug_ref, args.extra_notes)
    if args.vt_dcid:
        notes = f"[{args.vt_dcid}] {notes}"

    try:
        if is_configured():
            resp = _record_via_rest(
                vt_uuid=args.vt_uuid,
                vt_dcid=args.vt_dcid,
                result=args.result,
                notes=notes,
                log_full=log_full,
                executor=args.executor,
                environment=args.environment,
            )
        else:
            resp = _record_via_mcp(
                vt_uuid=args.vt_uuid,
                notes=notes,
                result=args.result,
                executor=args.executor,
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
