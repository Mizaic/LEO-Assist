"""Phase 2c -- Apply manual decisions for the 39 low-confidence DIs.

Phase 1 (`phase1_di_merge.py`) merged local DIs' acceptance_criteria
into their CSV-recorded Atlas counterparts using the `phase3-di-merge-gap`
list. That list inherited fuzzy matches from the original ID-mapping
script. Subsequent human review of the 39 `low-confidence` DIs in
`design-controls/atlas-id-mapping.csv` (and the report at
`design-controls/phase8-low-confidence-di-review.md`) showed that
nearly all of those Phase 1 targets are semantically wrong. This
script:

  1. Loads manual decisions from `phase2_decisions.json` for the 39
     low-confidence DI local IDs.
  2. For every wrong-target Atlas DI that received a Phase 1 AC merge,
     rolls back the polluted ACs (those whose normalised key matches a
     local DI AC).
  3. For each local DI:
        - decision == confirm (no override needed): no Atlas mutation.
        - decision == remap (different atlas_dc_id): updates the
          mapping CSV row only -- the new target keeps its current
          Atlas ACs untouched, since cross-merge would re-pollute it.
        - decision == create: creates a new Atlas DI with the local
          content via `create_design_input`, links it to its parent
          UN(s) via `link_design_controls`, and updates the mapping
          CSV.

Outputs:
  - design-controls/phase8c-low-confidence-action.csv (per-DI ledger)
  - design-controls/phase8c-low-confidence-action.md  (human summary)
  - scripts/atlas/.phase2c_low_confidence_state.json  (resume state)

Usage:
  python3 scripts/atlas/phase2c_low_confidence_action.py            # dry-run
  python3 scripts/atlas/phase2c_low_confidence_action.py --live     # mutate
  python3 scripts/atlas/phase2c_low_confidence_action.py --filter DI-LEO-AI-004
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
MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
DI_DIR = REPO / "design-controls" / "design-inputs"
UN_DIR = REPO / "design-controls" / "user-needs"
DECISIONS_PATH = REPO / "scripts" / "atlas" / "phase2_decisions.json"
LEDGER_CSV = REPO / "design-controls" / "phase8c-low-confidence-action.csv"
LEDGER_MD = REPO / "design-controls" / "phase8c-low-confidence-action.md"
STATE_PATH = REPO / "scripts" / "atlas" / ".phase2c_low_confidence_state.json"
PHASE2_STATE = REPO / "scripts" / "atlas" / ".phase2_un_di_state.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- text + AC utilities ---------------------------------------------


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _ac_key(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return " ".join(cleaned.split())


# -- local YAML loaders ----------------------------------------------


def _load_yaml_doc(path: Path, target_id: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    docs = list(yaml.safe_load_all(path.read_text()))
    for doc in docs:
        if not doc:
            continue
        if isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict) and item.get("id") == target_id:
                    return item
        elif isinstance(doc, dict) and doc.get("id") == target_id:
            return doc
    return None


def load_local_di(local_id: str) -> dict[str, Any] | None:
    item = _load_yaml_doc(DI_DIR / f"{local_id}.yaml", local_id)
    if not item:
        return None
    machine = item.get("machine_spec") or {}
    raw_ac = machine.get("acceptance_criteria") or []
    ac: list[str] = []
    for entry in raw_ac:
        if isinstance(entry, dict):
            ac.append(_norm_text(entry.get("spec") or entry.get("description")))
        else:
            ac.append(_norm_text(entry))
    ac = [s for s in ac if s]
    return {
        "id": item.get("id"),
        "title": _norm_text(item.get("title")),
        "requirement": _norm_text(item.get("requirement")),
        "rationale": _norm_text(item.get("rationale")),
        "input_type": (item.get("type") or "").strip().lower() or "functional",
        "verification_method": (
            item.get("verification") or {}
        ).get("method") or "Test",
        "safety_class": (item.get("safety_class") or "").strip().upper() or None,
        "acceptance_criteria": ac,
        "derived_from": list(item.get("derived_from") or []),
    }


# -- mapping CSV access ----------------------------------------------


def load_mapping_rows() -> list[dict[str, str]]:
    with MAPPING_CSV.open() as f:
        return list(csv.DictReader(f))


def write_mapping_rows(rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with MAPPING_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_un_mapping(rows: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in rows:
        if r.get("artefact_type") == "UN":
            local = r.get("local_id") or ""
            atlas = r.get("atlas_id") or ""
            if local and atlas:
                out[local] = atlas
    decisions = json.loads(DECISIONS_PATH.read_text())
    for lid, dec in decisions.items():
        if (
            isinstance(dec, dict)
            and lid.startswith("UN-LEO-AI-")
            and dec.get("decision") == "remap"
            and dec.get("atlas_dc_id")
        ):
            out[lid] = dec["atlas_dc_id"]
    state = (
        json.loads(PHASE2_STATE.read_text()) if PHASE2_STATE.exists() else {}
    )
    for lid, info in (state.get("created_uns") or {}).items():
        if isinstance(info, dict) and info.get("dcId"):
            out[lid] = info["dcId"]
    return out


# -- state ------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "started_at": None,
            "updated_at": None,
            "rollbacks": {},   # atlas_dc_id -> result
            "actions": {},     # local_id -> result row
        }
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


# -- Atlas operations -------------------------------------------------


def fetch_atlas_di(dc_id: str) -> dict[str, Any]:
    res = mcp.call_tool(
        "get_design_control",
        {"dc_type": "design-input", "dc_id": dc_id},
    )
    return res.get("designInput") or {}


def rollback_pollution(
    atlas_dc_id: str, local_ac: list[str], live: bool, state: dict[str, Any]
) -> dict[str, Any]:
    """Remove ACs that came from the wrongly-merged local DI."""
    out: dict[str, Any] = {
        "atlas_dc_id": atlas_dc_id, "kept": 0, "removed": 0,
        "result": "", "error": "",
    }
    cached = state["rollbacks"].get(atlas_dc_id)
    if cached and cached.get("result", "").startswith(("rolled-back", "noop")):
        out.update(cached)
        out["result"] = f"cached: {cached['result']}"
        return out
    try:
        di = fetch_atlas_di(atlas_dc_id)
    except mcp.McpError as e:
        out["result"] = "fetch_error"
        out["error"] = str(e)[:300]
        return out
    atlas_uuid = di.get("id")
    current_ac = di.get("acceptance_criteria") or []
    local_keys = {_ac_key(a) for a in local_ac if _ac_key(a)}
    keep: list[str] = []
    removed = 0
    for ac in current_ac:
        if _ac_key(ac) in local_keys:
            removed += 1
            continue
        keep.append(ac)
    out["kept"] = len(keep)
    out["removed"] = removed
    if removed == 0:
        out["result"] = "noop (nothing to roll back)"
        state["rollbacks"][atlas_dc_id] = out
        return out
    if not live:
        out["result"] = f"dry-run: would remove {removed}, keep {len(keep)}"
        return out
    if not atlas_uuid:
        out["result"] = "update_error"
        out["error"] = "atlas designInput missing UUID"
        return out
    try:
        mcp.call_tool(
            "update_design_input",
            {"dc_id": atlas_uuid, "acceptance_criteria": keep},
        )
        out["result"] = f"rolled-back -{removed} ACs ({len(keep)} kept)"
    except mcp.McpError as e:
        out["result"] = "update_error"
        out["error"] = str(e)[:300]
    state["rollbacks"][atlas_dc_id] = out
    return out


def create_atlas_di(
    local: dict[str, Any],
    parent_un_dc_ids: list[str],
    live: bool,
) -> dict[str, Any]:
    """Create a new Atlas DI with full local content, link parents."""
    out: dict[str, Any] = {
        "result": "", "error": "", "new_dc_id": "", "new_uuid": "",
        "linked_uns": 0,
    }
    if not live:
        out["result"] = "dry-run: would create"
        return out
    args: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "title": local["title"][:200] or local["id"],
        "description": local["requirement"] or local["title"],
    }
    if local.get("rationale"):
        args["rationale"] = local["rationale"]
    if local.get("input_type"):
        args["input_type"] = local["input_type"]
    if local.get("verification_method"):
        args["verification_method"] = local["verification_method"].lower()
    if local.get("acceptance_criteria"):
        args["acceptance_criteria"] = local["acceptance_criteria"]
    if local.get("safety_class") in ("A", "B"):
        args["safety_class"] = local["safety_class"]
    try:
        res = mcp.call_tool("create_design_input", args)
    except mcp.McpError as e:
        out["result"] = "create_error"
        out["error"] = str(e)[:600]
        return out
    new_di = res.get("designInput") or res.get("design_input") or res
    out["new_dc_id"] = new_di.get("dcId") or new_di.get("dc_id") or ""
    out["new_uuid"] = new_di.get("id") or ""
    if not out["new_dc_id"]:
        out["result"] = "create_error"
        out["error"] = f"unexpected response shape: {str(res)[:200]}"
        return out
    if parent_un_dc_ids:
        try:
            mcp.call_tool(
                "link_design_controls",
                {
                    "source_ids": parent_un_dc_ids,
                    "target_ids": [out["new_dc_id"]],
                    "relationship": "HAS_DESIGN_INPUT",
                },
            )
            out["linked_uns"] = len(parent_un_dc_ids)
            out["result"] = f"created+linked({len(parent_un_dc_ids)} UNs)"
        except mcp.McpError as e:
            out["result"] = "created (link_error)"
            out["error"] = str(e)[:300]
    else:
        out["result"] = "created (no parent UN)"
    return out


# -- main -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--filter", type=str, default="")
    parser.add_argument(
        "--skip-rollback",
        action="store_true",
        help="Skip the pollution rollback step (only execute remap/create)",
    )
    args = parser.parse_args()

    decisions_all: dict[str, Any] = json.loads(DECISIONS_PATH.read_text())
    rows = load_mapping_rows()
    low_conf = [
        r for r in rows
        if r.get("artefact_type") == "DI"
        and r.get("match_type") == "low-confidence"
    ]
    if args.filter:
        low_conf = [r for r in low_conf if r.get("local_id") == args.filter]
    print(
        f"Phase 2c scope: {len(low_conf)} low-confidence DIs "
        f"(live={args.live}, skip_rollback={args.skip_rollback})"
    )

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    un_mapping = load_un_mapping(rows)
    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()

    ledger: list[dict[str, Any]] = []
    rows_by_local = {r["local_id"]: r for r in rows}

    for idx, row in enumerate(low_conf, start=1):
        lid = row["local_id"]
        wrong_atlas = row["atlas_id"]
        decision_obj = decisions_all.get(lid) or {}
        decision = decision_obj.get("decision", "")
        target_atlas = decision_obj.get("atlas_dc_id") or ""

        result_row: dict[str, Any] = {
            "local_id": lid,
            "wrong_atlas": wrong_atlas,
            "decision": decision or "(missing)",
            "target_atlas": target_atlas,
            "rollback_result": "",
            "action_result": "",
            "new_dc_id": "",
            "error": "",
        }
        local = load_local_di(lid)
        if not local:
            result_row["action_result"] = "skip: local YAML missing"
            ledger.append(result_row)
            continue
        if not decision:
            result_row["action_result"] = "skip: no decision in JSON"
            ledger.append(result_row)
            continue

        is_confirm = (
            decision == "remap" and target_atlas == wrong_atlas
        )
        do_rollback = not args.skip_rollback and not is_confirm

        if do_rollback:
            rb = rollback_pollution(wrong_atlas, local["acceptance_criteria"],
                                    args.live, state)
            result_row["rollback_result"] = rb["result"]
            if rb.get("error"):
                result_row["error"] = rb["error"]
            save_state(state)
            time.sleep(0.05)
        else:
            result_row["rollback_result"] = (
                "skipped (confirm)" if is_confirm else "skipped (--skip-rollback)"
            )

        if decision == "remap":
            if target_atlas == wrong_atlas:
                result_row["action_result"] = "confirmed (no remap needed)"
            else:
                rows_by_local[lid]["atlas_id"] = target_atlas
                rows_by_local[lid]["match_type"] = "remap-manual"
                rows_by_local[lid]["notes"] = (
                    f"Phase 2c manual remap from {wrong_atlas}: "
                    f"{decision_obj.get('note', '')[:200]}"
                )
                result_row["action_result"] = (
                    f"remapped {wrong_atlas} -> {target_atlas}"
                )
        elif decision == "create":
            cached = state["actions"].get(lid)
            if cached and cached.get("new_dc_id"):
                result_row["new_dc_id"] = cached["new_dc_id"]
                result_row["action_result"] = (
                    f"created earlier ({cached['new_dc_id']})"
                )
            else:
                parent_dcids = [
                    un_mapping[pun] for pun in (local.get("derived_from") or [])
                    if pun in un_mapping
                ]
                cr = create_atlas_di(local, parent_dcids, args.live)
                result_row["action_result"] = cr["result"]
                if cr.get("error"):
                    prev = result_row["error"]
                    result_row["error"] = (
                        prev + " | " + cr["error"] if prev else cr["error"]
                    )
                if cr.get("new_dc_id"):
                    result_row["new_dc_id"] = cr["new_dc_id"]
                    rows_by_local[lid]["atlas_id"] = cr["new_dc_id"]
                    rows_by_local[lid]["match_type"] = "created-in-atlas"
                    rows_by_local[lid]["notes"] = (
                        f"Phase 2c manual create after low-confidence review. "
                        f"Replaces wrong target {wrong_atlas}."
                    )
                    state["actions"][lid] = {
                        "new_dc_id": cr["new_dc_id"],
                        "new_uuid": cr["new_uuid"],
                    }
                save_state(state)
            time.sleep(0.05)
        else:
            result_row["action_result"] = f"skip: unknown decision '{decision}'"

        print(
            f"[{idx}/{len(low_conf)}] {lid} ({decision}): "
            f"rb={result_row['rollback_result']} | "
            f"act={result_row['action_result']}"
        )
        ledger.append(result_row)

    if args.live:
        write_mapping_rows(rows)
        print(f"Updated mapping CSV: {MAPPING_CSV}")

    save_state(state)
    write_ledger(ledger)
    print(f"Wrote ledger: {LEDGER_CSV}")
    print(f"Wrote summary: {LEDGER_MD}")
    return 0


def write_ledger(rows: list[dict[str, Any]]) -> None:
    fields = [
        "local_id", "wrong_atlas", "decision", "target_atlas",
        "rollback_result", "action_result", "new_dc_id", "error",
    ]
    with LEDGER_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    counts: dict[str, int] = {}
    for r in rows:
        key = r.get("decision", "")
        counts[key] = counts.get(key, 0) + 1

    md = ["# Phase 2c -- Low-Confidence DI Action Ledger", "",
          f"Run at: {_now_iso()}",
          f"Total rows: {len(rows)}", "",
          "## Decision counts", ""]
    for k in sorted(counts):
        md.append(f"- `{k}`: {counts[k]}")
    md += ["", "## Rows", "",
           "| Local | Wrong target | Decision | Target | Rollback | Action | New DC | Error |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                str(r.get(k, "")).replace("|", "\\|")
                for k in (
                    "local_id", "wrong_atlas", "decision", "target_atlas",
                    "rollback_result", "action_result", "new_dc_id", "error",
                )
            )
            + " |"
        )
    LEDGER_MD.write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    sys.exit(main())
