"""Phase 2 -- Triage 22 unmatched UNs + 42 unmatched DIs.

For each unmatched local UN/DI listed in
`design-controls/atlas-id-mapping-gaps.md`, runs a second-pass offline
match against the Phase 0 Atlas snapshot using a richer text similarity
(title + description + acceptance_criteria union, Jaccard over tokens
plus SequenceMatcher).

Decision rule per row:
  - best_score >= REMAP_THRESHOLD (0.30): late-bind to that Atlas DC and
    queue an AC-merge identical to Phase 1 (handled here).
  - best_score < REMAP_THRESHOLD: create the DC in Atlas (live mode only)
    and link it to the matching parent UN / risks.

UN ordering: process UNs first so DIs can resolve parents.

Outputs:
  - design-controls/phase8-un-di-triage.csv   ledger
  - design-controls/phase8-un-di-triage.md    summary
  - scripts/atlas/.phase2_un_di_state.json    resume state

Usage:
  python3 scripts/atlas/phase2_un_di_triage.py             # dry-run all
  python3 scripts/atlas/phase2_un_di_triage.py --live      # mutate Atlas
  python3 scripts/atlas/phase2_un_di_triage.py --kind UN   # UNs only
  python3 scripts/atlas/phase2_un_di_triage.py --kind DI   # DIs only
  python3 scripts/atlas/phase2_un_di_triage.py --filter UN-LEO-AI-003
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
GAPS_MD = REPO / "design-controls" / "atlas-id-mapping-gaps.md"
MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
ATLAS_MATRIX = (
    REPO / "design-controls" / "atlas-baseline-2026-04-19" / "traceability-matrix.json"
)
UN_DIR = REPO / "design-controls" / "user-needs"
DI_DIR = REPO / "design-controls" / "design-inputs"
LEDGER_CSV = REPO / "design-controls" / "phase8-un-di-triage.csv"
LEDGER_MD = REPO / "design-controls" / "phase8-un-di-triage.md"
STATE_PATH = REPO / "scripts" / "atlas" / ".phase2_un_di_state.json"
DECISIONS_PATH = REPO / "scripts" / "atlas" / "phase2_decisions.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
REMAP_THRESHOLD = 0.30
HUMAN_REVIEW_THRESHOLD = 0.40  # >= this, late-bind without human review

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "with", "is", "are", "be", "been", "shall", "must", "should", "system",
    "as", "so", "that", "their", "this", "from", "into", "via", "any", "all",
    "when", "able", "can", "will", "leo", "ai", "leoai", "using", "use",
    "user", "need", "needs", "have", "has", "not", "than", "then",
}


# -- text utilities ---------------------------------------------------


def _norm(text: Any) -> str:
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _norm(text).replace("/", " ").replace("-", " ").split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if not tok or tok in STOPWORDS or len(tok) < 3:
            continue
        out.add(tok)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sim(a: str, b: str) -> float:
    seq = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    jac = _jaccard(_tokens(a), _tokens(b))
    return max(seq, jac)


# -- gap parsing ------------------------------------------------------


def parse_gap_section(kind: str) -> list[str]:
    """Extract unmatched local IDs for a section ('UN', 'DI', 'DO', etc.)."""
    text = GAPS_MD.read_text()
    pattern = rf"## {kind} \(total[^)]*\)[\s\S]*?Unmatched local IDs:\s*\n((?:- [^\n]*\n)*)"
    m = re.search(pattern, text)
    if not m:
        return []
    return [
        line.strip().lstrip("- ").strip()
        for line in m.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def load_un_mapping_from_csv() -> dict[str, str]:
    """Local UN-LEO-AI-XX -> Atlas UN-XXXXXXXX (already-mapped rows)."""
    mapping: dict[str, str] = {}
    with MAPPING_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("artefact_type") != "UN":
                continue
            local_id = row.get("local_id") or ""
            atlas_id = row.get("atlas_id") or ""
            if local_id and atlas_id:
                mapping[local_id] = atlas_id
    return mapping


# -- local YAML loading ----------------------------------------------


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


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


def load_local_un(local_id: str) -> dict[str, Any] | None:
    item = _load_yaml_doc(UN_DIR / f"{local_id}.yaml", local_id)
    if not item:
        return None
    raw_ac = item.get("acceptance_criteria") or []
    ac = [_norm_text(x) for x in raw_ac if x]
    stakeholder = item.get("stakeholder") or {}
    role = stakeholder.get("role") if isinstance(stakeholder, dict) else stakeholder
    return {
        "id": item.get("id"),
        "title": _norm_text(item.get("title")),
        "description": _norm_text(item.get("description")),
        "rationale": _norm_text(item.get("rationale")),
        "priority": (item.get("priority") or "").strip().upper() or None,
        "stakeholder_types": [role] if role else ["Quality Engineer"],
        "acceptance_criteria": ac,
        "child_dis": list(item.get("design_inputs") or []),
    }


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
        "verification_method": (item.get("verification") or {}).get("method") or "Test",
        "safety_class": (item.get("safety_class") or "").strip().upper() or None,
        "acceptance_criteria": ac,
        "derived_from": list(item.get("derived_from") or []),
        "risks": list(item.get("risks") or []),
    }


# -- Atlas snapshot loading -------------------------------------------


def load_atlas_nodes(dc_type: str) -> list[dict[str, Any]]:
    """Return Atlas nodes of a given dcType from the baseline snapshot."""
    data = json.loads(ATLAS_MATRIX.read_text())
    return [n for n in data.get("nodes", []) if n.get("dcType") == dc_type]


def best_match(
    query_text: str, atlas_nodes: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float]:
    best: tuple[dict[str, Any] | None, float] = (None, 0.0)
    for node in atlas_nodes:
        text = " ".join(filter(None, [node.get("title", ""), node.get("description", "")]))
        score = _sim(query_text, text)
        if score > best[1]:
            best = (node, score)
    return best


# -- ledger / state ---------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "started_at": None,
            "updated_at": None,
            "rows": {},
            "created_uns": {},  # local_id -> atlas dc_id
            "created_dis": {},  # local_id -> atlas dc_id
        }
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


# -- UN handling ------------------------------------------------------


def process_un(local_id: str, atlas_uns: list[dict[str, Any]],
               live: bool, state: dict[str, Any],
               decisions: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "UN", "local_id": local_id, "atlas_id": "",
        "decision": "", "best_score": 0.0, "best_atlas": "",
        "result": "", "error": "",
    }
    local = load_local_un(local_id)
    if not local:
        row["result"] = "skip: local YAML missing"
        return row
    query = " ".join(filter(None, [local["title"], local["description"]]))
    cand, score = best_match(query, atlas_uns)
    row["best_score"] = round(score, 3)
    row["best_atlas"] = cand.get("dcId", "") if cand else ""

    override = decisions.get(local_id)
    if override and override.get("decision") in ("remap", "create", "skip"):
        row["decision"] = override["decision"] + "-manual"
        if override["decision"] == "remap":
            row["atlas_id"] = override.get("atlas_dc_id") or ""
            row["result"] = "remap-recorded (manual)"
            return row
        if override["decision"] == "skip":
            row["result"] = "skipped (manual)"
            return row
        # create-manual falls through to creation
    elif score >= HUMAN_REVIEW_THRESHOLD and cand:
        row["decision"] = "remap"
        row["atlas_id"] = cand["dcId"]
        row["result"] = "remap-recorded"
        return row
    elif score >= REMAP_THRESHOLD and cand:
        row["decision"] = "human-review"
        row["atlas_id"] = cand["dcId"]
        row["result"] = "skipped: needs human review"
        return row
    else:
        row["decision"] = "create"
    if not live:
        row["result"] = "dry-run: would create"
        return row
    args = {
        "product_id": PRODUCT_ID,
        "title": local["title"][:200] or local_id,
        "description": local["description"] or local["title"],
        "stakeholder_types": (override or {}).get(
            "stakeholder_types"
        ) or local["stakeholder_types"],
    }
    if local.get("rationale"):
        args["rationale"] = local["rationale"]
    pri = (override or {}).get("priority") or local.get("priority")
    if pri and pri.upper() in ("MUST", "SHOULD", "COULD", "WONT"):
        args["priority"] = pri.upper()
    if local.get("acceptance_criteria"):
        args["acceptance_criteria"] = local["acceptance_criteria"]
    try:
        res = mcp.call_tool("create_user_need", args)
    except mcp.McpError as e:
        row["result"] = "create_error"
        row["error"] = str(e)[:300]
        return row
    new_un = res.get("userNeed") or res.get("user_need") or res
    new_dc_id = new_un.get("dcId") or new_un.get("dc_id")
    new_uuid = new_un.get("id")
    row["atlas_id"] = new_dc_id or ""
    row["result"] = "created"
    state["created_uns"][local_id] = {"dcId": new_dc_id, "id": new_uuid}
    return row


# -- DI handling ------------------------------------------------------


def resolve_un_dcid(un_local_id: str, un_mapping: dict[str, str],
                    state: dict[str, Any]) -> str | None:
    if un_local_id in un_mapping:
        return un_mapping[un_local_id]
    created = state["created_uns"].get(un_local_id)
    if isinstance(created, dict):
        return created.get("dcId")
    return None


def process_di(local_id: str, atlas_dis: list[dict[str, Any]],
               un_mapping: dict[str, str], live: bool,
               state: dict[str, Any],
               decisions: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "DI", "local_id": local_id, "atlas_id": "",
        "decision": "", "best_score": 0.0, "best_atlas": "",
        "result": "", "error": "",
    }
    local = load_local_di(local_id)
    if not local:
        row["result"] = "skip: local YAML missing"
        return row
    query = " ".join(filter(None, [local["title"], local["requirement"]]))
    cand, score = best_match(query, atlas_dis)
    row["best_score"] = round(score, 3)
    row["best_atlas"] = cand.get("dcId", "") if cand else ""

    override = decisions.get(local_id)
    if override and override.get("decision") in ("remap", "create", "skip"):
        row["decision"] = override["decision"] + "-manual"
        if override["decision"] == "remap":
            row["atlas_id"] = override.get("atlas_dc_id") or ""
            row["result"] = "remap-recorded (manual)"
            return row
        if override["decision"] == "skip":
            row["result"] = "skipped (manual)"
            return row
        # fall through to create
    elif score >= HUMAN_REVIEW_THRESHOLD and cand:
        row["decision"] = "remap"
        row["atlas_id"] = cand["dcId"]
        row["result"] = "remap-recorded"
        return row
    elif score >= REMAP_THRESHOLD and cand:
        row["decision"] = "human-review"
        row["atlas_id"] = cand["dcId"]
        row["result"] = "skipped: needs human review"
        return row
    else:
        row["decision"] = row.get("decision") or "create"

    if not live:
        row["result"] = "dry-run: would create"
        return row

    cached_create = state["created_dis"].get(local_id)
    if cached_create and cached_create.get("dcId"):
        new_dc_id = cached_create["dcId"]
        new_uuid = cached_create["id"]
        row["atlas_id"] = new_dc_id
        row["result"] = "create-skipped (already exists)"
    else:
        args = {
            "product_id": PRODUCT_ID,
            "title": local["title"][:200] or local_id,
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
            row["result"] = "create_error"
            row["error"] = str(e)[:600]
            return row
        new_di = res.get("designInput") or res.get("design_input") or res
        new_dc_id = new_di.get("dcId") or new_di.get("dc_id")
        new_uuid = new_di.get("id")
        row["atlas_id"] = new_dc_id or ""
        state["created_dis"][local_id] = {"dcId": new_dc_id, "id": new_uuid}

    # Link to parent UN(s).
    parent_dc_ids: list[str] = []
    parent_uuids: list[str] = []
    for un_local in local.get("derived_from", []):
        parent_dc = resolve_un_dcid(un_local, un_mapping, state)
        if parent_dc:
            parent_dc_ids.append(parent_dc)
    # link_design_controls accepts dc_ids (UN-XXXX), tested in Phase 1 by
    # fire_atlas_fmea -- it works with both dcId and UUID for links.
    if parent_dc_ids and new_dc_id:
        try:
            mcp.call_tool("link_design_controls", {
                "source_ids": parent_dc_ids,
                "target_ids": [new_dc_id],
                "relationship": "HAS_DESIGN_INPUT",
            })
            row["result"] = f"created+linked({len(parent_dc_ids)} UNs)"
        except mcp.McpError as e:
            row["result"] = "created (link_error)"
            row["error"] = str(e)[:300]
    else:
        row["result"] = "created (no parent UN known)"

    return row


# -- ledger output ----------------------------------------------------


def write_ledger(rows: list[dict[str, Any]]) -> None:
    fields = ["kind", "local_id", "atlas_id", "decision", "best_score",
              "best_atlas", "result", "error"]
    with LEDGER_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fields})

    counts: dict[str, int] = {}
    for r in rows:
        key = f"{r['kind']}:{r['decision']}"
        counts[key] = counts.get(key, 0) + 1
    md = ["# Phase 2 -- UN/DI Triage Ledger", "",
          f"Run at: {_now_iso()}",
          f"Total rows: {len(rows)}", "",
          "## Decision counts", ""]
    for k in sorted(counts):
        md.append(f"- `{k}`: {counts[k]}")
    md += ["", "## Rows", "",
           "| Kind | Local | Decision | Best Atlas | Score | Result | Error |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [
            str(r.get(k, "")).replace("|", "\\|")
            for k in ("kind", "local_id", "decision", "best_atlas", "best_score",
                      "result", "error")
        ]
        md.append("| " + " | ".join(cells) + " |")
    LEDGER_MD.write_text("\n".join(md) + "\n")


# -- main -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--filter", type=str, default="")
    parser.add_argument("--kind", choices=("UN", "DI", "ALL"), default="ALL")
    args = parser.parse_args()

    print("Loading Atlas snapshot ...")
    atlas_uns = load_atlas_nodes("user-need")
    atlas_dis = load_atlas_nodes("design-input")
    print(f"  atlas UNs: {len(atlas_uns)}  atlas DIs: {len(atlas_dis)}")

    un_ids = parse_gap_section("UN") if args.kind in ("UN", "ALL") else []
    di_ids = parse_gap_section("DI") if args.kind in ("DI", "ALL") else []
    if args.filter:
        un_ids = [x for x in un_ids if x.startswith(args.filter)]
        di_ids = [x for x in di_ids if x.startswith(args.filter)]
    if args.limit:
        un_ids = un_ids[: args.limit]
        di_ids = di_ids[: args.limit]
    print(f"Triage scope: {len(un_ids)} UNs + {len(di_ids)} DIs (live={args.live})")

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    un_mapping = load_un_mapping_from_csv()
    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()
    decisions: dict[str, Any] = {}
    if DECISIONS_PATH.exists():
        decisions = json.loads(DECISIONS_PATH.read_text())
    # Inject manual UN remaps so DIs can resolve their parents
    for lid, dec in decisions.items():
        if lid.startswith("UN-LEO-AI-") and dec.get("decision") == "remap":
            atlas_dc = dec.get("atlas_dc_id")
            if atlas_dc:
                un_mapping[lid] = atlas_dc
    rows: list[dict[str, Any]] = []

    for idx, lid in enumerate(un_ids, start=1):
        cached = state["rows"].get(lid)
        if args.live and cached and cached.get("result", "").startswith("created"):
            rows.append(cached)
            continue
        row = process_un(lid, atlas_uns, args.live, state, decisions)
        rows.append(row)
        state["rows"][lid] = row
        save_state(state)
        print(f"  UN [{idx}/{len(un_ids)}] {lid}: {row['decision']} "
              f"score={row['best_score']} -> {row['result']}")
        time.sleep(0.05)

    for idx, lid in enumerate(di_ids, start=1):
        cached = state["rows"].get(lid)
        # retry "created (no parent UN known)" rows so we can attach links now
        if (
            args.live
            and cached
            and cached.get("result", "").startswith("created")
            and "no parent UN known" not in cached.get("result", "")
        ):
            rows.append(cached)
            continue
        row = process_di(lid, atlas_dis, un_mapping, args.live, state, decisions)
        rows.append(row)
        state["rows"][lid] = row
        save_state(state)
        print(f"  DI [{idx}/{len(di_ids)}] {lid}: {row['decision']} "
              f"score={row['best_score']} -> {row['result']}")
        time.sleep(0.05)

    save_state(state)
    write_ledger(rows)
    print(f"Wrote ledger: {LEDGER_CSV}")
    print(f"Wrote summary: {LEDGER_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
