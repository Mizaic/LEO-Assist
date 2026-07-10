"""Phase 1 -- Merge local DI improvements into the 109 matched Atlas DIs.

Reads the (local_id, atlas_id) pairs from
`design-controls/phase3-di-merge-gap.md`, fetches each Atlas DI via
`get_design_control`, computes a conservative merge plan, and (in --live
mode) applies it via `update_design_input`.

Conservative rules (Atlas wins unless local is strictly additive):
  - AC: dedup-union of (atlas + local). Push only if union > current.
  - Rationale: push local rationale only if Atlas value is empty/null.
  - Description: push local SHALL only if Atlas description is empty/null.
  - safety_class: push local class only if Atlas value is empty/null.
  - Class C: never auto-promote (would require class_c_override_rationale).

Outputs:
  - design-controls/phase7-di-merge-execution.csv  (per-DI ledger)
  - design-controls/phase7-di-merge-execution.md   (human summary)
  - scripts/atlas/.phase1_di_merge_state.json      (resume-safe state)

Usage:
  python3 scripts/atlas/phase1_di_merge.py                # dry-run, all 109
  python3 scripts/atlas/phase1_di_merge.py --limit 5      # sample dry-run
  python3 scripts/atlas/phase1_di_merge.py --filter DI-LEO-AI-001
  python3 scripts/atlas/phase1_di_merge.py --live         # mutate Atlas
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
GAP_REPORT = REPO / "design-controls" / "phase3-di-merge-gap.md"
DI_DIR = REPO / "design-controls" / "design-inputs"
LEDGER_CSV = REPO / "design-controls" / "phase7-di-merge-execution.csv"
LEDGER_MD = REPO / "design-controls" / "phase7-di-merge-execution.md"
STATE_PATH = REPO / "scripts" / "atlas" / ".phase1_di_merge_state.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402
from product import PRODUCT_ID  # noqa: E402,F401

# -- gap report parsing -----------------------------------------------


GAP_LINE_RE = re.compile(r"^\|\s*(DI-LEO-AI-\d+)\s*\|\s*(DI-[0-9A-F]{8})\s*\|")


def load_gap_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    text = GAP_REPORT.read_text()
    for line in text.splitlines():
        m = GAP_LINE_RE.match(line)
        if m:
            pairs.append((m.group(1), m.group(2)))
    return pairs


# -- local YAML parsing -----------------------------------------------


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def load_local_di(local_id: str) -> dict[str, Any] | None:
    path = DI_DIR / f"{local_id}.yaml"
    if not path.exists():
        return None
    docs = list(yaml.safe_load_all(path.read_text()))
    for doc in docs:
        if not doc:
            continue
        if isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict) and item.get("id") == local_id:
                    return _flatten_local(item)
        elif isinstance(doc, dict) and doc.get("id") == local_id:
            return _flatten_local(doc)
    return None


def _flatten_local(item: dict[str, Any]) -> dict[str, Any]:
    machine = item.get("machine_spec") or {}
    raw_ac = machine.get("acceptance_criteria") or []
    ac_strings: list[str] = []
    for ac in raw_ac:
        if isinstance(ac, dict):
            ac_strings.append(_norm_text(ac.get("spec") or ac.get("description")))
        else:
            ac_strings.append(_norm_text(ac))
    ac_strings = [s for s in ac_strings if s]
    return {
        "id": item.get("id"),
        "title": _norm_text(item.get("title")),
        "requirement": _norm_text(item.get("requirement")),
        "rationale": _norm_text(item.get("rationale")),
        "safety_class": (item.get("safety_class") or "").strip().upper() or None,
        "acceptance_criteria": ac_strings,
    }


# -- merge logic ------------------------------------------------------


def _ac_key(text: str) -> str:
    """Normalised key for AC dedup -- lowercase alnum + spaces only."""
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return " ".join(cleaned.split())


def union_ac(atlas_ac: list[str], local_ac: list[str]) -> list[str]:
    """Atlas-first union. Adds local entries that have no key collision."""
    seen: set[str] = set()
    out: list[str] = []
    for ac in atlas_ac:
        k = _ac_key(ac)
        if k and k not in seen:
            seen.add(k)
            out.append(ac.strip())
    for ac in local_ac:
        k = _ac_key(ac)
        if k and k not in seen:
            seen.add(k)
            out.append(ac.strip())
    return out


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def build_update_plan(local: dict[str, Any], atlas: dict[str, Any]) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "actions": [],
        "update_args": {},
        "skipped": [],
    }

    atlas_ac = atlas.get("acceptance_criteria") or []
    local_ac = local.get("acceptance_criteria") or []
    merged_ac = union_ac(atlas_ac, local_ac)
    if len(merged_ac) > len(atlas_ac):
        added = len(merged_ac) - len(atlas_ac)
        plan["update_args"]["acceptance_criteria"] = merged_ac
        plan["actions"].append(
            f"AC: +{added} (atlas {len(atlas_ac)} -> {len(merged_ac)})"
        )
    else:
        plan["skipped"].append(
            f"AC: no additions (atlas {len(atlas_ac)} >= union {len(merged_ac)})"
        )

    if is_empty(atlas.get("rationale")) and not is_empty(local.get("rationale")):
        plan["update_args"]["rationale"] = local["rationale"]
        plan["actions"].append("rationale: empty -> populated")
    else:
        plan["skipped"].append("rationale: atlas already populated")

    if is_empty(atlas.get("description")) and not is_empty(local.get("requirement")):
        plan["update_args"]["description"] = local["requirement"]
        plan["actions"].append("description: empty -> populated with local SHALL")
    else:
        plan["skipped"].append("description: atlas already populated")

    atlas_class = (atlas.get("safety_class") or "").strip().upper() or None
    local_class = (local.get("safety_class") or "").strip().upper() or None
    if not atlas_class and local_class:
        if local_class == "C":
            plan["skipped"].append(
                "safety_class: would set 'C' -- requires class_c_override_rationale "
                "(skipped, needs human)"
            )
        elif local_class in ("A", "B"):
            plan["update_args"]["safety_class"] = local_class
            plan["actions"].append(f"safety_class: empty -> {local_class}")
    else:
        plan["skipped"].append(
            f"safety_class: atlas={atlas_class} local={local_class} -- no change"
        )

    return plan


# -- ledger / state ---------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"started_at": None, "updated_at": None, "rows": {}}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


# -- main loop --------------------------------------------------------


def process_pair(
    local_id: str,
    atlas_id: str,
    live: bool,
    state: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "local_id": local_id,
        "atlas_id": atlas_id,
        "actions": "",
        "skipped": "",
        "result": "",
        "error": "",
    }
    local = load_local_di(local_id)
    if not local:
        row["result"] = "skip: local YAML missing"
        return row
    try:
        atlas_resp = mcp.call_tool(
            "get_design_control",
            {"dc_type": "design-input", "dc_id": atlas_id},
        )
    except mcp.McpError as e:
        row["result"] = "fetch_error"
        row["error"] = str(e)[:300]
        return row

    di = atlas_resp.get("designInput") or {}
    atlas_uuid = di.get("id")
    atlas_view = {
        "uuid": atlas_uuid,
        "title": di.get("title"),
        "description": di.get("description"),
        "rationale": di.get("rationale"),
        "safety_class": di.get("safety_class"),
        "acceptance_criteria": di.get("acceptance_criteria") or [],
    }
    plan = build_update_plan(local, atlas_view)
    row["actions"] = " | ".join(plan["actions"]) if plan["actions"] else "no-op"
    row["skipped"] = " | ".join(plan["skipped"])

    if not plan["update_args"]:
        row["result"] = "noop"
        return row

    if not live:
        row["result"] = "dry-run"
        return row

    if not atlas_uuid:
        row["result"] = "update_error"
        row["error"] = "atlas designInput missing 'id' (UUID)"
        return row

    args = {"dc_id": atlas_uuid, **plan["update_args"]}
    try:
        mcp.call_tool("update_design_input", args)
        row["result"] = "updated"
    except mcp.McpError as e:
        row["result"] = "update_error"
        row["error"] = str(e)[:300]
    return row


def write_ledger(rows: list[dict[str, Any]]) -> None:
    fields = ["local_id", "atlas_id", "actions", "skipped", "result", "error"]
    with LEDGER_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    md_lines = [
        "# Phase 1 -- DI Merge Execution Ledger",
        "",
        f"Run at: {_now_iso()}",
        f"Total rows: {len(rows)}",
        "",
        "## Result counts",
        "",
    ]
    for k in sorted(counts):
        md_lines.append(f"- `{k}`: {counts[k]}")
    md_lines.extend(
        [
            "",
            "## Per-DI detail",
            "",
            "| Local | Atlas | Result | Actions | Skipped | Error |",
            "|---|---|---|---|---|---|",
        ]
    )
    for r in rows:
        md_lines.append(
            "| {local_id} | {atlas_id} | {result} | {actions} | {skipped} | {error} |".format(
                **{
                    k: str(r.get(k, "")).replace("|", "\\|")
                    for k in [
                        "local_id",
                        "atlas_id",
                        "result",
                        "actions",
                        "skipped",
                        "error",
                    ]
                }
            )
        )
    LEDGER_MD.write_text("\n".join(md_lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Apply updates via update_design_input."
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Process at most N pairs (0 = all)."
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="",
        help="Process only pairs whose local_id matches this prefix.",
    )
    args = parser.parse_args()

    pairs = load_gap_pairs()
    if args.filter:
        pairs = [p for p in pairs if p[0].startswith(args.filter)]
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"Processing {len(pairs)} pairs (live={args.live})")

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()

    rows: list[dict[str, Any]] = []
    for idx, (local_id, atlas_id) in enumerate(pairs, start=1):
        cached = state["rows"].get(local_id)
        if args.live and cached and cached.get("result") == "updated":
            rows.append(cached)
            continue
        row = process_pair(local_id, atlas_id, args.live, state)
        rows.append(row)
        state["rows"][local_id] = row
        if idx % 5 == 0 or idx == len(pairs):
            save_state(state)
            print(
                f"  [{idx}/{len(pairs)}] {local_id} -> {atlas_id} : "
                f"{row['result']} {row['actions']}"
            )
        time.sleep(0.05)

    save_state(state)
    write_ledger(rows)
    print(f"Wrote ledger: {LEDGER_CSV}")
    print(f"Wrote summary: {LEDGER_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
