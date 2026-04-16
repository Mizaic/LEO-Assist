"""
Fire pre-generated Atlas risk payloads once the enhanced /api/risks endpoint is deployed.

Usage:
  python3 fire_atlas_risks.py --file atlas_risk_payloads_gap.json --atlas-url https://your-atlas-url --token YOUR_TOKEN
  python3 fire_atlas_risks.py --file atlas_risk_payloads_gap.json --dry-run

Options:
  --file       Path to the payloads JSON file (default: atlas_risk_payloads_gap.json)
  --atlas-url  Base URL of Atlas API (default: reads ATLAS_URL env var)
  --token      Bearer token (default: reads ATLAS_TOKEN env var)
  --dry-run    Print payloads without sending
  --resume     Skip entries that already have a risk_id in the state file
  --state      Path to state file tracking created IDs (default: .fire_state.json)

The script writes a state file after each successful create so it can be safely
re-run on failure without creating duplicates.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        with state_path.open() as f:
            return json.load(f)
    return {}


def save_state(state_path: Path, state: dict) -> None:
    with state_path.open("w") as f:
        json.dump(state, f, indent=2)


def strip_meta_fields(body: dict) -> dict:
    """Remove underscore-prefixed internal fields before sending to API."""
    return {k: v for k, v in body.items() if not k.startswith("_")}


def post(url: str, body: dict, token: str) -> tuple[int, dict]:
    import urllib.request
    import urllib.error

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        return e.code, {"error": body_text}


def log(msg: str) -> None:
    print(msg, flush=True)


def process_entry(
    entry: dict,
    atlas_url: str,
    token: str,
    state: dict,
    state_path: Path,
    dry_run: bool,
) -> bool:
    fmea_id = entry["fmea_id"]

    if fmea_id in state:
        log(f"  SKIP  {fmea_id} -- already created (risk_id={state[fmea_id]['risk_id']})")
        return True

    create_body = strip_meta_fields(entry["create"])

    if dry_run:
        log(f"  DRY   {fmea_id}  {create_body['title'][:60]}")
        log(f"        link_un={entry['link_un']}")
        if entry.get("link_dis"):
            log(f"        link_dis={entry['link_dis']}")
        return True

    log(f"  POST  {fmea_id}  {create_body['title'][:60]} ...")
    status, resp = post(f"{atlas_url}/api/risks", create_body, token)

    if status not in (200, 201):
        log(f"  FAIL  {fmea_id}  HTTP {status}: {str(resp)[:120]}")
        return False

    risk_id = resp.get("id") or resp.get("risk_id") or resp.get("data", {}).get("id")
    if not risk_id:
        log(f"  FAIL  {fmea_id}  Could not extract risk ID from response: {resp}")
        return False

    log(f"  OK    {fmea_id}  -> {risk_id}")

    state[fmea_id] = {"risk_id": risk_id, "fmea_id": fmea_id}
    save_state(state_path, state)

    _link(risk_id, entry["link_un"], atlas_url, token, fmea_id, "UN")
    if entry.get("link_dis"):
        _link(risk_id, entry["link_dis"], atlas_url, token, fmea_id, "DIs")

    time.sleep(0.15)
    return True


def _link(
    risk_id: str,
    link_body: dict,
    atlas_url: str,
    token: str,
    fmea_id: str,
    label: str,
) -> None:
    status, resp = post(
        f"{atlas_url}/api/risks/{risk_id}/links", link_body, token
    )
    if status in (200, 201, 204):
        log(f"        LINKED {label}")
    else:
        log(f"        LINK WARN {label} HTTP {status}: {str(resp)[:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fire Atlas risk payloads")
    parser.add_argument(
        "--file",
        default="atlas_risk_payloads_gap.json",
        help="Payload JSON file",
    )
    parser.add_argument(
        "--atlas-url",
        default=os.environ.get("ATLAS_URL", ""),
        help="Atlas base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("ATLAS_TOKEN", ""),
        help="Bearer token",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--state",
        default=".fire_state.json",
        help="State file path",
    )
    args = parser.parse_args()

    if not args.dry_run:
        if not args.atlas_url:
            print("ERROR: --atlas-url or ATLAS_URL env var required")
            sys.exit(1)
        if not args.token:
            print("ERROR: --token or ATLAS_TOKEN env var required")
            sys.exit(1)

    payload_path = Path(args.file)
    if not payload_path.exists():
        print(f"ERROR: {payload_path} not found -- run generate_atlas_risk_payloads.py first")
        sys.exit(1)

    with payload_path.open() as f:
        entries = json.load(f)

    state_path = Path(args.state)
    state = load_state(state_path)

    log(f"Loaded {len(entries)} entries from {payload_path.name}")
    log(f"State file: {state_path} ({len(state)} already created)")
    log(f"Dry run: {args.dry_run}")
    log("")

    ok = fail = skip = 0
    for entry in entries:
        if entry["fmea_id"] in state:
            skip += 1
            log(f"  SKIP  {entry['fmea_id']} (already in state)")
            continue
        if process_entry(
            entry, args.atlas_url, args.token, state, state_path, args.dry_run
        ):
            ok += 1
        else:
            fail += 1

    log("")
    log(f"Done -- OK={ok}  SKIP={skip}  FAIL={fail}")
    if fail:
        log("Re-run to retry failed entries (state file preserves successes).")
        sys.exit(1)


if __name__ == "__main__":
    main()
