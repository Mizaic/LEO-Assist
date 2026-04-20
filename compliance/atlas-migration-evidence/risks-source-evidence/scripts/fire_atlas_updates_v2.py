"""Replay update_risk only for the rewritten v2 payloads.

Reads atlas_fmea_payloads_v2.json and .fire_state_v2.json (which holds the
already-known risk_id per master_id), then calls update_risk via the Atlas
MCP for every record. Skips records that have no rewrite_provenance.

Resume-safe: writes step_text_v2: ok per record after success.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the proven HTTP transport from fire_atlas_fmea.py
sys.path.insert(0, str(Path(__file__).parent))
import fire_atlas_fmea as fa  # noqa: E402

ROOT = Path("/Users/robsmith/Documents/github/LEO-AI-CORE/design-controls/risks")
PAYLOAD_V2_PATH = ROOT / "atlas_fmea_payloads_v2.json"
STATE_PATH = ROOT / ".fire_state_v2.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _push_one(record: dict, risk_id: str) -> tuple[bool, str]:
    args = {"risk_id": risk_id, **record["update_risk"]}
    try:
        fa._call_tool("update_risk", args)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]


def main() -> int:
    payload = json.loads(PAYLOAD_V2_PATH.read_text())
    records = payload["records"]
    state = json.loads(STATE_PATH.read_text())
    fired = state.get("fired", {})

    print(f"Loaded {len(records)} v2 records.")
    print("Initializing MCP session ...")
    fa._initialize()

    ok = 0
    skipped = 0
    failed: list[tuple[str, str]] = []

    for idx, rec in enumerate(records, start=1):
        mid = rec["master_id"]
        if not rec.get("rewrite_provenance"):
            skipped += 1
            continue
        entry = fired.get(mid)
        if not entry or not entry.get("risk_id"):
            failed.append((mid, "no risk_id in state"))
            continue
        if entry.get("step_text_v2") == "ok":
            ok += 1
            continue
        success, err = _push_one(rec, entry["risk_id"])
        if success:
            entry["step_text_v2"] = "ok"
            entry["step_text_v2_at"] = _now_iso()
            ok += 1
        else:
            entry["step_text_v2"] = f"fail: {err}"
            failed.append((mid, err))
        if idx % 10 == 0 or idx == len(records):
            state["last_updated_at"] = _now_iso()
            STATE_PATH.write_text(json.dumps(state, indent=2))
            print(
                f"Progress: {idx}/{len(records)}  "
                f"ok={ok} skipped={skipped} failed={len(failed)}",
                flush=True,
            )

    state["last_updated_at"] = _now_iso()
    STATE_PATH.write_text(json.dumps(state, indent=2))

    print(
        f"\nDONE  ok={ok} skipped={skipped} failed={len(failed)}"
    )
    if failed:
        print("Failures:")
        for mid, err in failed[:20]:
            print(f"  - {mid}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
