"""Phase 3 -- Migrate local DOs and VTs into Atlas.

Atlas baseline shows 156 design-outputs and 179 verification-tests but
NONE of the 130 local DOs or 149 local VTs were matched (even fuzzily)
by the original mapping script -- their titles and IDs are too
different to ID-match. This script:

  1. Loads each local DO/VT YAML and computes a richer text key
     (title + description + acceptance text + source/test paths).
  2. Computes the best Atlas baseline match using SequenceMatcher
     and Jaccard token overlap.
  3. Decision rule:
        - score >= REMAP_HARD (0.55)     -> remap (record only, no
                                              AC merge -- Phase 1 taught
                                              us not to merge across
                                              fuzzy matches).
        - REMAP_SOFT (0.40) <= score
              < REMAP_HARD               -> human review (skipped).
        - score < REMAP_SOFT             -> create new in Atlas.
  4. For CREATE rows in --live mode:
        - DO: create_design_output, then link_design_controls
              IMPLEMENTS source_ids=[DO_dcId]
              target_ids=[parent_DI_atlas_dcIds].
        - VT: create_verification_test, then
              link_design_controls VERIFIES source_ids=[VT_dcId]
              target_ids=[parent_DI_atlas_dcIds];
              and TESTS source_ids=[VT_dcId]
              target_ids=[parent_DO_atlas_dcIds].
  5. For REMAP rows: only update mapping CSV; no Atlas mutation.
  6. For VTs whose local YAML has status=passed AND at least one
     execution_history entry with result=pass, call
     record_verification_run on the resulting Atlas VT (--record-runs
     flag, separate from --live to keep responsibilities clear).

Outputs:
  - design-controls/phase9-do-migration.csv / .md
  - design-controls/phase9-vt-migration.csv / .md
  - design-controls/phase9-vt-runs.csv (record_verification_run ledger)
  - scripts/atlas/.phase3_do_state.json
  - scripts/atlas/.phase3_vt_state.json
  - scripts/atlas/.phase3_vt_runs_state.json

Usage:
  python3 scripts/atlas/phase3_do_vt_migrate.py --kind DO            # dry-run DOs
  python3 scripts/atlas/phase3_do_vt_migrate.py --kind DO --live     # mutate
  python3 scripts/atlas/phase3_do_vt_migrate.py --kind VT --live
  python3 scripts/atlas/phase3_do_vt_migrate.py --kind VT --record-runs
  python3 scripts/atlas/phase3_do_vt_migrate.py --kind ALL --live --record-runs
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
from typing import Any, Iterable

import yaml

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
DO_DIR = REPO / "design-controls" / "design-outputs"
VT_DIR = REPO / "design-controls" / "verification-tests"
ATLAS_MATRIX = (
    REPO / "design-controls" / "atlas-baseline-2026-04-19" / "traceability-matrix.json"
)
DECISIONS_PATH = REPO / "scripts" / "atlas" / "phase3_decisions.json"

DO_LEDGER_CSV = REPO / "design-controls" / "phase9-do-migration.csv"
DO_LEDGER_MD = REPO / "design-controls" / "phase9-do-migration.md"
VT_LEDGER_CSV = REPO / "design-controls" / "phase9-vt-migration.csv"
VT_LEDGER_MD = REPO / "design-controls" / "phase9-vt-migration.md"
VT_RUN_LEDGER = REPO / "design-controls" / "phase9-vt-runs.csv"

DO_STATE_PATH = REPO / "scripts" / "atlas" / ".phase3_do_state.json"
VT_STATE_PATH = REPO / "scripts" / "atlas" / ".phase3_vt_state.json"
VT_RUN_STATE_PATH = REPO / "scripts" / "atlas" / ".phase3_vt_runs_state.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402
from product import PRODUCT_ID  # noqa: E402

REMAP_HARD = 0.55  # auto-remap (record only, no merge)
REMAP_SOFT = 0.40  # >=this needs review; create otherwise

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "in",
    "on",
    "at",
    "by",
    "with",
    "is",
    "are",
    "be",
    "been",
    "shall",
    "must",
    "should",
    "system",
    "as",
    "so",
    "that",
    "their",
    "this",
    "from",
    "into",
    "via",
    "any",
    "all",
    "when",
    "able",
    "can",
    "will",
    "leo",
    "ai",
    "leoai",
    "using",
    "use",
    "user",
    "need",
    "needs",
    "have",
    "has",
    "not",
    "than",
    "then",
    "test",
    "tests",
    "verify",
    "verifies",
    "verification",
    "design",
    "output",
}


# -- text helpers -----------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(text: Any) -> str:
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in (
        _norm(text).replace("/", " ").replace("-", " ").replace(".", " ").split()
    ):
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


# -- mapping CSV helpers ----------------------------------------------


def load_mapping_rows() -> list[dict[str, str]]:
    with MAPPING_CSV.open() as f:
        return list(csv.DictReader(f))


def write_mapping_rows(rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with MAPPING_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def load_di_mapping() -> dict[str, str]:
    """local DI-LEO-AI-* -> Atlas dcId."""
    out: dict[str, str] = {}
    for r in load_mapping_rows():
        if r.get("artefact_type") != "DI":
            continue
        local = r.get("local_id") or ""
        atlas = r.get("atlas_id") or ""
        if local and atlas:
            out[local] = atlas
    return out


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


def _stringify_acceptance(items: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for entry in items or []:
        if isinstance(entry, dict):
            for key in ("criterion", "spec", "description", "name"):
                value = entry.get(key)
                if value:
                    out.append(_norm_text(value))
                    break
        elif entry is not None:
            out.append(_norm_text(entry))
    return [s for s in out if s]


def _coerce_id_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def load_local_do(local_id: str) -> dict[str, Any] | None:
    item = _load_yaml_doc(DO_DIR / f"{local_id}.yaml", local_id)
    if not item:
        return None
    spec = item.get("specification") or {}
    impl = item.get("implementation") or {}
    arts = impl.get("artifacts") or []
    paths: list[str] = []
    for art in arts:
        if isinstance(art, dict) and art.get("location"):
            paths.append(_norm_text(art.get("location")))
    for art in item.get("implementation_artefacts") or []:
        if isinstance(art, dict) and art.get("path"):
            paths.append(_norm_text(art["path"]))
    for art in item.get("deliverables") or []:
        if isinstance(art, dict) and art.get("file"):
            paths.append(_norm_text(art["file"]))
    for art in item.get("components") or []:
        if isinstance(art, dict) and art.get("file"):
            paths.append(_norm_text(art["file"]))
    safety = (
        (item.get("safety_characteristics") or {}).get("safety_class")
        or item.get("safety_class")
        or ""
    )
    out_type = item.get("type") or "Software_Module"
    title = spec.get("title") or item.get("title") or item.get("id")
    description = spec.get("description") or item.get("description") or ""
    parents = (
        ((item.get("traceability") or {}).get("design_inputs"))
        or _coerce_id_list(item.get("derived_from"))
        or _coerce_id_list(item.get("satisfies"))
        or []
    )
    return {
        "id": item.get("id"),
        "title": _norm_text(title),
        "description": _norm_text(description),
        "purpose": _norm_text(spec.get("purpose")),
        "acceptance_criteria": _stringify_acceptance(spec.get("acceptance_criteria")),
        "source_paths": paths,
        "output_type": (out_type or "").lower().replace("_", " ").strip(),
        "safety_class": (safety or "").upper().strip() or None,
        "design_inputs": list(parents),
    }


def load_local_vt(local_id: str) -> dict[str, Any] | None:
    item = _load_yaml_doc(VT_DIR / f"{local_id}.yaml", local_id)
    if not item:
        return None
    meta = item.get("metadata") or {}
    paths = list(meta.get("test_file_paths") or [])
    test_cases = item.get("test_cases") or []
    case_names = [
        _norm_text(tc.get("case_name") or tc.get("case_id"))
        for tc in test_cases
        if isinstance(tc, dict)
    ]
    case_names = [s for s in case_names if s]
    protocol_steps: list[str] = []
    for tc in test_cases[:3]:
        if not isinstance(tc, dict):
            continue
        for step in (tc.get("test_steps") or [])[:3]:
            if isinstance(step, dict) and step.get("action"):
                protocol_steps.append(_norm_text(step["action"]))
    last_run = ""
    for entry in item.get("execution_history") or []:
        if isinstance(entry, dict) and entry.get("result"):
            last_run = (entry.get("result") or "").lower()
    return {
        "id": item.get("id"),
        "title": _norm_text(meta.get("title") or item.get("id")),
        "description": _norm_text(meta.get("description")),
        "test_type": (meta.get("test_type") or "functional").lower(),
        "test_level": (meta.get("test_level") or "unit").lower(),
        "automation_status": (meta.get("automation_status") or "").lower(),
        "automation_framework": (meta.get("automation_framework") or "").lower(),
        "verification_method": "test",
        "safety_class": (meta.get("safety_class") or "").upper().strip() or None,
        "acceptance_criteria": case_names,
        "protocol_steps": protocol_steps,
        "test_file_paths": paths,
        "design_inputs": list(
            ((item.get("traceability") or {}).get("design_inputs")) or []
        ),
        "design_outputs": list(
            ((item.get("traceability") or {}).get("design_outputs")) or []
        ),
        "status": (item.get("status") or "").lower().strip(),
        "last_run_result": last_run,
    }


# -- Atlas baseline loader -------------------------------------------


def load_atlas_nodes(dc_type: str) -> list[dict[str, Any]]:
    data = json.loads(ATLAS_MATRIX.read_text())
    return [n for n in data.get("nodes", []) if n.get("dcType") == dc_type]


def best_match(
    query_text: str, atlas_nodes: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float]:
    best: tuple[dict[str, Any] | None, float] = (None, 0.0)
    for node in atlas_nodes:
        text = " ".join(
            filter(None, [node.get("title", ""), node.get("description", "")])
        )
        score = _sim(query_text, text)
        if score > best[1]:
            best = (node, score)
    return best


# -- state ------------------------------------------------------------


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "started_at": None,
            "updated_at": None,
            "rows": {},
            "created": {},  # local_id -> {dcId, id}
        }
    return json.loads(path.read_text())


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


# -- decision logic ---------------------------------------------------


def make_decision(
    score: float, candidate: dict[str, Any] | None, override: dict[str, Any] | None
) -> tuple[str, str, str]:
    """Return (decision, atlas_dc_id, note). decision in {remap, create, review, skip}."""
    if override and override.get("decision") in ("remap", "create", "skip", "review"):
        atlas = override.get("atlas_dc_id") or (
            candidate.get("dcId") if candidate else ""
        )
        return override["decision"], atlas, "manual"
    if candidate and score >= REMAP_HARD:
        return "remap", candidate["dcId"], "auto >= REMAP_HARD"
    if candidate and score >= REMAP_SOFT:
        return "review", candidate["dcId"], "auto in soft band"
    return "create", "", "auto < REMAP_SOFT"


# -- DO migration -----------------------------------------------------


def process_do(
    local_id: str,
    atlas_dos: list[dict[str, Any]],
    di_mapping: dict[str, str],
    live: bool,
    state: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "DO",
        "local_id": local_id,
        "atlas_id": "",
        "decision": "",
        "best_score": 0.0,
        "best_atlas": "",
        "linked_dis": 0,
        "result": "",
        "error": "",
    }
    local = load_local_do(local_id)
    if not local:
        row["result"] = "skip: local YAML missing"
        return row
    query = " ".join(
        filter(
            None,
            [
                local["title"],
                local["description"],
                local["purpose"],
                " ".join(local["source_paths"]),
            ],
        )
    )
    cand, score = best_match(query, atlas_dos)
    row["best_score"] = round(score, 3)
    row["best_atlas"] = cand.get("dcId", "") if cand else ""

    decision, atlas_dc, note = make_decision(score, cand, decisions.get(local_id))
    row["decision"] = decision + ("-manual" if note == "manual" else "")
    row["atlas_id"] = atlas_dc

    if decision == "remap":
        row["result"] = "remap-recorded"
        return row
    if decision == "skip":
        row["result"] = "skipped (manual)"
        return row
    if decision == "review":
        row["result"] = "skipped: needs human review"
        return row

    if not live:
        row["result"] = "dry-run: would create"
        return row

    cached = state["created"].get(local_id)
    if cached and cached.get("dcId"):
        new_dc_id = cached["dcId"]
        row["atlas_id"] = new_dc_id
        row["result"] = "create-skipped (already exists)"
    else:
        args: dict[str, Any] = {
            "product_id": PRODUCT_ID,
            "title": local["title"][:200] or local_id,
            "description": local["description"] or local["purpose"] or local["title"],
        }
        if local.get("acceptance_criteria"):
            args["acceptance_criteria"] = local["acceptance_criteria"]
        if local.get("output_type"):
            args["output_type"] = local["output_type"]
        if local.get("source_paths"):
            args["source_reference"] = ", ".join(local["source_paths"][:5])[:500]
        if local.get("safety_class") in ("A", "B"):
            args["safety_class"] = local["safety_class"]
        try:
            res = mcp.call_tool("create_design_output", args)
        except mcp.McpError as e:
            row["result"] = "create_error"
            row["error"] = str(e)[:600]
            return row
        new_do = res.get("designOutput") or res.get("design_output") or res
        new_dc_id = new_do.get("dcId") or new_do.get("dc_id") or ""
        new_uuid = new_do.get("id") or ""
        row["atlas_id"] = new_dc_id
        if not new_dc_id:
            row["result"] = "create_error"
            row["error"] = f"unexpected response: {str(res)[:200]}"
            return row
        state["created"][local_id] = {"dcId": new_dc_id, "id": new_uuid}

    parent_dc_ids = [
        di_mapping[di] for di in (local.get("design_inputs") or []) if di in di_mapping
    ]
    if parent_dc_ids:
        try:
            mcp.call_tool(
                "link_design_controls",
                {
                    "source_ids": [new_dc_id],
                    "target_ids": parent_dc_ids,
                    "relationship": "IMPLEMENTS",
                },
            )
            row["linked_dis"] = len(parent_dc_ids)
            row["result"] = f"created+linked({len(parent_dc_ids)} DIs)"
        except mcp.McpError as e:
            row["result"] = "created (link_error)"
            row["error"] = str(e)[:300]
    else:
        row["result"] = "created (no parent DI)"
    return row


# -- VT migration -----------------------------------------------------


def process_vt(
    local_id: str,
    atlas_vts: list[dict[str, Any]],
    di_mapping: dict[str, str],
    do_mapping: dict[str, str],
    live: bool,
    state: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "VT",
        "local_id": local_id,
        "atlas_id": "",
        "decision": "",
        "best_score": 0.0,
        "best_atlas": "",
        "linked_dis": 0,
        "linked_dos": 0,
        "result": "",
        "error": "",
    }
    local = load_local_vt(local_id)
    if not local:
        row["result"] = "skip: local YAML missing"
        return row
    query = " ".join(
        filter(
            None,
            [local["title"], local["description"], " ".join(local["test_file_paths"])],
        )
    )
    cand, score = best_match(query, atlas_vts)
    row["best_score"] = round(score, 3)
    row["best_atlas"] = cand.get("dcId", "") if cand else ""

    decision, atlas_dc, note = make_decision(score, cand, decisions.get(local_id))
    row["decision"] = decision + ("-manual" if note == "manual" else "")
    row["atlas_id"] = atlas_dc

    if decision == "remap":
        row["result"] = "remap-recorded"
        return row
    if decision == "skip":
        row["result"] = "skipped (manual)"
        return row
    if decision == "review":
        row["result"] = "skipped: needs human review"
        return row

    if not live:
        row["result"] = "dry-run: would create"
        return row

    cached = state["created"].get(local_id)
    if cached and cached.get("dcId"):
        new_dc_id = cached["dcId"]
        row["atlas_id"] = new_dc_id
        row["result"] = "create-skipped (already exists)"
    else:
        args: dict[str, Any] = {
            "product_id": PRODUCT_ID,
            "title": local["title"][:200] or local_id,
            "description": local["description"] or local["title"],
        }
        if local.get("test_type"):
            args["test_type"] = local["test_type"]
        if local.get("verification_method"):
            args["verification_method"] = local["verification_method"]
        if local.get("acceptance_criteria"):
            args["acceptance_criteria"] = local["acceptance_criteria"][:25]
        if local.get("protocol_steps"):
            args["protocol_steps"] = local["protocol_steps"][:25]
        if local.get("safety_class") in ("A", "B"):
            args["safety_class"] = local["safety_class"]
        try:
            res = mcp.call_tool("create_verification_test", args)
        except mcp.McpError as e:
            row["result"] = "create_error"
            row["error"] = str(e)[:600]
            return row
        new_vt = res.get("verificationTest") or res.get("verification_test") or res
        new_dc_id = new_vt.get("dcId") or new_vt.get("dc_id") or ""
        new_uuid = new_vt.get("id") or ""
        row["atlas_id"] = new_dc_id
        if not new_dc_id:
            row["result"] = "create_error"
            row["error"] = f"unexpected response: {str(res)[:200]}"
            return row
        state["created"][local_id] = {"dcId": new_dc_id, "id": new_uuid}

    parent_dis = [
        di_mapping[di] for di in (local.get("design_inputs") or []) if di in di_mapping
    ]
    if parent_dis:
        try:
            mcp.call_tool(
                "link_design_controls",
                {
                    "source_ids": [new_dc_id],
                    "target_ids": parent_dis,
                    "relationship": "VERIFIES",
                },
            )
            row["linked_dis"] = len(parent_dis)
        except mcp.McpError as e:
            row["error"] = (
                row["error"] + " | " if row["error"] else ""
            ) + f"VERIFIES: {str(e)[:200]}"

    parent_dos = [
        do_mapping[do] for do in (local.get("design_outputs") or []) if do in do_mapping
    ]
    if parent_dos:
        try:
            mcp.call_tool(
                "link_design_controls",
                {
                    "source_ids": [new_dc_id],
                    "target_ids": parent_dos,
                    "relationship": "TESTS",
                },
            )
            row["linked_dos"] = len(parent_dos)
        except mcp.McpError as e:
            row["error"] = (
                row["error"] + " | " if row["error"] else ""
            ) + f"TESTS: {str(e)[:200]}"

    pieces: list[str] = ["created"]
    if row["linked_dis"]:
        pieces.append(f"+{row['linked_dis']} DI")
    if row["linked_dos"]:
        pieces.append(f"+{row['linked_dos']} DO")
    row["result"] = (
        " ".join(pieces) if len(pieces) > 1 else "created (no parents linked)"
    )
    return row


# -- record_verification_run -----------------------------------------


def _resolve_vt_uuid(dc_id: str, info: dict[str, Any], state: dict[str, Any]) -> str:
    """Return the Atlas verification-test UUID, fetching once and caching."""
    uuid = info.get("id") or info.get("uuid")
    if uuid:
        return uuid
    cache = state.setdefault("uuid_cache", {})
    if dc_id in cache:
        return cache[dc_id]
    try:
        res = mcp.call_tool(
            "get_design_control",
            {"dc_type": "verification-test", "dc_id": dc_id},
        )
    except mcp.McpError:
        return ""
    vt = res.get("verificationTest") or {}
    uuid = vt.get("id") or ""
    if uuid:
        cache[dc_id] = uuid
    return uuid


def record_runs(vt_state: dict[str, Any], live: bool) -> list[dict[str, Any]]:
    """Call record_verification_run for every local VT with status=passed."""
    state = (
        json.loads(VT_RUN_STATE_PATH.read_text())
        if VT_RUN_STATE_PATH.exists()
        else {"recorded": {}}
    )
    state.setdefault("uuid_cache", {})
    # Pre-seed: VT-LEO-AI-001 had a probe run created during UUID
    # debugging. Mark as already-recorded so we don't double-record.
    state["recorded"].setdefault(
        "VT-LEO-AI-001",
        {
            "atlas_dc_id": "VT-BF1C6463",
            "at": "2026-04-19T00:00:00Z",
            "note": "probe call during UUID debugging",
        },
    )
    rows: list[dict[str, Any]] = []
    items = sorted(vt_state.get("created", {}).items())
    print(f"record_runs: scanning {len(items)} created VTs")
    for idx, (local_id, info) in enumerate(items, start=1):
        out: dict[str, Any] = {
            "local_id": local_id,
            "atlas_dc_id": info.get("dcId", ""),
            "result": "",
            "error": "",
        }
        local = load_local_vt(local_id)
        if not local:
            out["result"] = "skip: local YAML missing"
            rows.append(out)
            continue
        if local.get("status") != "passed":
            out["result"] = f"skip: status={local.get('status') or 'unset'}"
            rows.append(out)
            continue
        if local.get("last_run_result") != "pass":
            out["result"] = (
                f"skip: no passing execution_history "
                f"(last={local.get('last_run_result') or 'none'})"
            )
            rows.append(out)
            continue
        if local_id in state["recorded"]:
            out["result"] = "cached: already recorded"
            rows.append(out)
            continue
        if not live:
            out["result"] = "dry-run: would record_verification_run"
            rows.append(out)
            continue
        atlas_dc = info.get("dcId")
        if not atlas_dc:
            out["result"] = "skip: missing atlas dcId"
            rows.append(out)
            continue
        atlas_uuid = _resolve_vt_uuid(atlas_dc, info, state)
        if not atlas_uuid:
            out["result"] = "skip: could not resolve UUID"
            rows.append(out)
            continue
        try:
            mcp.call_tool(
                "record_verification_run",
                {
                    "vt_id": atlas_uuid,
                    "result": "pass",
                    "notes": (
                        f"Migrated from local {local_id} -- last local "
                        f"execution_history entry recorded result=pass."
                    )[:500],
                    "executed_by": "leo-atlas-migration",
                    "environment": "ci_cd",
                },
            )
            out["result"] = "recorded pass"
            state["recorded"][local_id] = {"atlas_dc_id": atlas_dc, "at": _now_iso()}
            VT_RUN_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
        except mcp.McpError as e:
            out["result"] = "record_error"
            out["error"] = str(e)[:300]
        print(f"  [{idx}/{len(items)}] {local_id}: {out['result']}")
        rows.append(out)
        time.sleep(0.05)
    return rows


# -- ledger output ----------------------------------------------------


def write_kind_ledger(
    rows: list[dict[str, Any]], csv_path: Path, md_path: Path, kind: str
) -> None:
    fields = [
        "kind",
        "local_id",
        "atlas_id",
        "decision",
        "best_score",
        "best_atlas",
        "linked_dis",
        "linked_dos",
        "result",
        "error",
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    counts: dict[str, int] = {}
    for r in rows:
        key = r.get("decision", "")
        counts[key] = counts.get(key, 0) + 1
    md = [
        f"# Phase 3 -- {kind} Migration Ledger",
        "",
        f"Run at: {_now_iso()}",
        f"Total rows: {len(rows)}",
        "",
        "## Decision counts",
        "",
    ]
    for k in sorted(counts):
        md.append(f"- `{k}`: {counts[k]}")
    md += [
        "",
        "## Rows",
        "",
        "| Local | Decision | Best Atlas | Score | Linked DI | Linked DO | Result | Error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                str(r.get(k, "")).replace("|", "\\|")
                for k in (
                    "local_id",
                    "decision",
                    "best_atlas",
                    "best_score",
                    "linked_dis",
                    "linked_dos",
                    "result",
                    "error",
                )
            )
            + " |"
        )
    md_path.write_text("\n".join(md) + "\n")


def write_run_ledger(rows: list[dict[str, Any]]) -> None:
    fields = ["local_id", "atlas_dc_id", "result", "error"]
    with VT_RUN_LEDGER.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def update_mapping_csv_with_results(
    rows: list[dict[str, Any]], artefact_type: str
) -> None:
    """Patch the mapping CSV with new atlas_id / match_type for processed rows."""
    csv_rows = load_mapping_rows()
    by_local = {(r["artefact_type"], r["local_id"]): r for r in csv_rows}
    changed = False
    for row in rows:
        key = (artefact_type, row["local_id"])
        target = by_local.get(key)
        if not target:
            continue
        new_atlas = row.get("atlas_id") or ""
        if not new_atlas:
            continue
        decision = row.get("decision", "")
        if "remap" in decision:
            new_match_type = "remap-manual" if "manual" in decision else "remap-fuzzy"
        elif decision.startswith("create"):
            new_match_type = "created-in-atlas"
        else:
            continue
        if (
            target.get("atlas_id") != new_atlas
            or target.get("match_type") != new_match_type
        ):
            target["atlas_id"] = new_atlas
            target["match_type"] = new_match_type
            note_prefix = "Phase 3"
            if "remap" in decision:
                note = f"{note_prefix} {new_match_type}"
            else:
                note = f"{note_prefix}: created in Atlas with full local YAML content"
            existing = target.get("notes") or ""
            target["notes"] = note if not existing else f"{note} | {existing[:200]}"
            changed = True
    if changed:
        write_mapping_rows(csv_rows)


# -- main -------------------------------------------------------------


def parse_gap_section(kind: str) -> list[str]:
    text = (REPO / "design-controls" / "atlas-id-mapping-gaps.md").read_text()
    pattern = (
        rf"## {kind} \(total[^)]*\)[\s\S]*?Unmatched local IDs:\s*\n((?:- [^\n]*\n)*)"
    )
    m = re.search(pattern, text)
    if not m:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in m.group(1).splitlines():
        if not line.strip().startswith("- "):
            continue
        local = line.strip().lstrip("- ").strip()
        if local and local not in seen:
            seen.add(local)
            out.append(local)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("DO", "VT", "ALL"), default="ALL")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--record-runs",
        action="store_true",
        help="After VT migration, call record_verification_run",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--filter", type=str, default="")
    args = parser.parse_args()

    decisions: dict[str, Any] = {}
    if DECISIONS_PATH.exists():
        decisions = json.loads(DECISIONS_PATH.read_text())

    print("Loading Atlas snapshot ...")
    atlas_dos = load_atlas_nodes("design-output") if args.kind in ("DO", "ALL") else []
    atlas_vts = (
        load_atlas_nodes("verification-test") if args.kind in ("VT", "ALL") else []
    )
    print(f"  atlas DOs: {len(atlas_dos)}  atlas VTs: {len(atlas_vts)}")

    di_mapping = load_di_mapping()
    print(f"  local DI -> atlas DI mapping rows: {len(di_mapping)}")

    do_local_ids = parse_gap_section("DO") if args.kind in ("DO", "ALL") else []
    vt_local_ids = parse_gap_section("VT") if args.kind in ("VT", "ALL") else []
    if args.filter:
        do_local_ids = [
            x for x in do_local_ids if x == args.filter or x.startswith(args.filter)
        ]
        vt_local_ids = [
            x for x in vt_local_ids if x == args.filter or x.startswith(args.filter)
        ]
    if args.limit:
        do_local_ids = do_local_ids[: args.limit]
        vt_local_ids = vt_local_ids[: args.limit]
    print(
        f"Migration scope: {len(do_local_ids)} DOs + {len(vt_local_ids)} VTs "
        f"(live={args.live}, record_runs={args.record_runs})"
    )

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    do_state = load_state(DO_STATE_PATH)
    vt_state = load_state(VT_STATE_PATH)
    if not do_state.get("started_at"):
        do_state["started_at"] = _now_iso()
    if not vt_state.get("started_at"):
        vt_state["started_at"] = _now_iso()

    do_rows: list[dict[str, Any]] = []
    for idx, lid in enumerate(do_local_ids, start=1):
        cached = do_state["rows"].get(lid)
        if (
            args.live
            and cached
            and cached.get("result", "").startswith(
                ("created", "create-skipped", "remap-recorded")
            )
        ):
            do_rows.append(cached)
            continue
        row = process_do(lid, atlas_dos, di_mapping, args.live, do_state, decisions)
        do_rows.append(row)
        do_state["rows"][lid] = row
        save_state(DO_STATE_PATH, do_state)
        print(
            f"  DO [{idx}/{len(do_local_ids)}] {lid}: {row['decision']} "
            f"score={row['best_score']} -> {row['result']}"
        )
        time.sleep(0.05)
    if do_local_ids:
        save_state(DO_STATE_PATH, do_state)
        write_kind_ledger(do_rows, DO_LEDGER_CSV, DO_LEDGER_MD, "DO")
        if args.live:
            update_mapping_csv_with_results(do_rows, "DO")
            print(f"DO mapping CSV patched.")
        print(f"Wrote DO ledger: {DO_LEDGER_CSV}")

    do_mapping = (
        load_di_mapping()
    )  # reload, but DOs aren't in CSV per artefact_type=='DI'
    do_local_to_atlas: dict[str, str] = {}
    for r in do_rows:
        if r.get("atlas_id"):
            do_local_to_atlas[r["local_id"]] = r["atlas_id"]
    # Also pull from any pre-existing mapping CSV rows (for DOs created on
    # earlier runs but missing from this run's scope due to --filter).
    for r in load_mapping_rows():
        if r.get("artefact_type") == "DO" and r.get("local_id") and r.get("atlas_id"):
            do_local_to_atlas.setdefault(r["local_id"], r["atlas_id"])

    vt_rows: list[dict[str, Any]] = []
    for idx, lid in enumerate(vt_local_ids, start=1):
        cached = vt_state["rows"].get(lid)
        if (
            args.live
            and cached
            and cached.get("result", "").startswith(
                ("created", "create-skipped", "remap-recorded")
            )
        ):
            vt_rows.append(cached)
            continue
        row = process_vt(
            lid,
            atlas_vts,
            di_mapping,
            do_local_to_atlas,
            args.live,
            vt_state,
            decisions,
        )
        vt_rows.append(row)
        vt_state["rows"][lid] = row
        save_state(VT_STATE_PATH, vt_state)
        print(
            f"  VT [{idx}/{len(vt_local_ids)}] {lid}: {row['decision']} "
            f"score={row['best_score']} -> {row['result']}"
        )
        time.sleep(0.05)
    if vt_local_ids:
        save_state(VT_STATE_PATH, vt_state)
        write_kind_ledger(vt_rows, VT_LEDGER_CSV, VT_LEDGER_MD, "VT")
        if args.live:
            update_mapping_csv_with_results(vt_rows, "VT")
            print(f"VT mapping CSV patched.")
        print(f"Wrote VT ledger: {VT_LEDGER_CSV}")

    if args.record_runs:
        run_rows = record_runs(vt_state, args.live)
        write_run_ledger(run_rows)
        print(f"Wrote VT-runs ledger: {VT_RUN_LEDGER}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
