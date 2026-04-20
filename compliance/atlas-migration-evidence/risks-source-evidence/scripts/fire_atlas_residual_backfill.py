"""Backfill residual_* fields on Atlas Risks already created from this repo.

Reads the regenerated atlas_fmea_payloads.json (which now carries residual
S/P/D/RPN/level/acceptability/justification for all 156 records) and the
.fire_state_v2.json that holds the Atlas risk UUIDs. Fires update_risk
once per record with ONLY the residual fields plus a refreshed
mitigation_effectiveness, so we don't accidentally re-write hazard text
that was edited in Atlas after the first push.

Resume-safe: writes step_residual_backfill: ok per master_id after
success and skips already-completed entries.

Usage:
    python3 fire_atlas_residual_backfill.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fire_atlas_fmea as fa  # noqa: E402

ROOT = Path(__file__).parent
PAYLOAD_PATH = ROOT / "atlas_fmea_payloads.json"
STATE_PATH = ROOT / ".fire_state_v2.json"

RESIDUAL_KEYS = (
    "residual_severity",
    "residual_probability",
    "residual_detectability",
    "residual_rpn",
    "residual_risk_level",
    "residual_acceptability",
    "residual_justification",
    "mitigation_effectiveness",
)

STATE_KEY = "step_residual_backfill"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _residual_args(record: dict, risk_id: str) -> dict | None:
    upd = record.get("update_risk") or {}
    args: dict = {"risk_id": risk_id}
    for key in RESIDUAL_KEYS:
        if key in upd and upd[key] not in (None, ""):
            args[key] = upd[key]
    if len(args) == 1:
        return None
    return args


def main() -> int:
    payload = json.loads(PAYLOAD_PATH.read_text())
    records = payload["records"]
    state = json.loads(STATE_PATH.read_text())
    fired = state.setdefault("fired", {})

    print(f"Loaded {len(records)} records.")
    print(f"Initializing MCP session at {fa.MCP_URL} ...")
    try:
        fa._initialize()
        print(f"MCP session id: {fa._SESSION_ID}")
    except Exception as exc:  # noqa: BLE001
        print(f"Initialize failed (continuing, server may be stateless): {exc}")

    ok = 0
    skipped = 0
    failed: list[tuple[str, str]] = []

    for idx, rec in enumerate(records, start=1):
        master_id = rec["master_id"]
        entry = fired.get(master_id) or {}
        risk_id = entry.get("risk_id")
        if not risk_id:
            skipped += 1
            continue
        if entry.get(STATE_KEY) == "ok":
            skipped += 1
            continue
        args = _residual_args(rec, risk_id)
        if args is None:
            skipped += 1
            entry[STATE_KEY] = "skip:no-residual"
            fired[master_id] = entry
            continue
        try:
            fa._call_tool("update_risk", args)
            entry[STATE_KEY] = "ok"
            entry[f"{STATE_KEY}_at"] = _now_iso()
            fired[master_id] = entry
            ok += 1
        except Exception as exc:  # noqa: BLE001
            entry[STATE_KEY] = f"fail: {str(exc)[:200]}"
            fired[master_id] = entry
            failed.append((master_id, str(exc)[:200]))
        if idx % 10 == 0:
            STATE_PATH.write_text(json.dumps(state, indent=2))
            print(
                f"Progress: {idx}/{len(records)} processed, "
                f"ok={ok} skipped={skipped} failed={len(failed)}",
                flush=True,
            )

    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(
        f"DONE: ok={ok} skipped={skipped} failed={len(failed)}"
    )
    if failed:
        print("Failed records:")
        for mid, msg in failed[:25]:
            print(f"  - {mid}: {msg}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
