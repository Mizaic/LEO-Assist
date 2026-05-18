"""Build the MVP-scope verification test backlog CSV.

Pulls the full Atlas traceability matrix once, filters UNs to MVP
releases (R1, R3, R4, R5, R7), and emits one CSV row per
(VT, DI, UN, release) tuple.

NOTE: Atlas server-side `search_design_controls` is currently
returning zero hits for every query, so R3/R4/R5/R7 UN discovery
is performed by local keyword matching against UN titles +
descriptions in the matrix. R1 is the explicit list from the brief.

Usage:
    python -m scripts.vt_execution.build_backlog [--out PATH]
                                                 [--no-cache-matrix]

ASCII only (.cursor/rules/ascii-only.mdc).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.atlas._mcp_transport import call_tool, initialize  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
DEFAULT_OUT = ROOT / "scripts" / "vt_execution" / "mvp_vt_backlog.csv"
CACHE_DIR = ROOT / "scripts" / "vt_execution" / ".cache"
MATRIX_CACHE = CACHE_DIR / "matrix.json"
DO_CACHE = CACHE_DIR / "do_source_refs.json"

# R1 - Referral pipeline (explicit list from the brief).
R1_UNS = [
    "UN-AA722A75", "UN-A949A642", "UN-C2F187E9", "UN-412D1ECD", "UN-65571220",
    "UN-30A82196", "UN-7913344A", "UN-FBBFD5CB", "UN-AFFA1FB3", "UN-575E8DCB",
    "UN-0374FE26", "UN-04E94B6F", "UN-79318B40", "UN-D7186F4F", "UN-EE9C8DC9",
    "UN-2D6BD78B", "UN-AA00A211", "UN-39591899", "UN-94BCC4DC", "UN-EAD58F62",
]

# R7 anchor + widget DIs.
R7_ANCHOR_UN = "UN-64F0E9C3"
R7_WIDGET_DIS = {
    "DI-85C95E53", "DI-A1206416", "DI-85944331",
    "DI-5F121122", "DI-3C06AFD0", "DI-2FBDAC7D",
}

# Keyword sets per release (lower-cased substring matching).
KEYWORDS: dict[str, list[str]] = {
    "R3": [
        "clinical review", "correction loop", "reviewer", "ask leo",
        "gold label", "assertion correction", "reviewer queue",
        "training feedback",
    ],
    "R4": [
        "knowledge author", "guideline rule", "terminology authoring",
        "approval workflow", "cso review", "deployment gate",
        "change request", "risk-prioritised triage", "rule activation",
    ],
    "R5": [
        "tenant onboarding", "user management", "audit log",
        "multi-tenant", "rbac", "ods sync",
        # 'admin' alone is too broad; include only if combined.
    ],
    "R7": ["widget", "embedding", " sdk", "browser sdk"],
}

# Release priority - first wins.
RELEASE_ORDER = ["R1", "R3", "R4", "R5", "R7"]

CSV_COLS = [
    "vt_dcid", "di_dcid", "un_dcid", "release",
    "framework", "automation_status",
    "test_file_path", "on_disk", "current_status",
    "owner", "run_started_at", "run_finished_at",
    "run_result", "run_log_path", "atlas_updated_at",
    "vt_uuid", "vt_title",
]

PATH_RE = re.compile(
    r"(?:^|[\s;,()`\"'\[])"
    r"((?:services|libs|scripts|tests|data|compliance|e2e)"
    r"/[A-Za-z0-9_./\-]+\.(?:py|tsx?|jsx?))"
)

_INITIALISED = False


def _ensure() -> None:
    global _INITIALISED
    if _INITIALISED:
        return
    initialize()
    _INITIALISED = True


def fetch_matrix(use_cache: bool) -> dict:
    if use_cache and MATRIX_CACHE.exists():
        print(f"  using cached matrix at {MATRIX_CACHE}")
        return json.loads(MATRIX_CACHE.read_text())
    _ensure()
    print("  fetching traceability matrix from Atlas (~25s) ...")
    t0 = time.time()
    out = call_tool(
        "get_traceability_matrix",
        {"product_id": PRODUCT_ID},
    )
    print(f"  matrix fetch ok in {time.time() - t0:.1f}s "
          f"(nodes={len(out.get('nodes', []))}, "
          f"links={len(out.get('links', []))}, "
          f"rows={len(out.get('rows', []))})")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MATRIX_CACHE.write_text(json.dumps(out))
    return out


def fetch_do_source_ref(do_dcid: str, cache: dict) -> dict:
    """Cached DO fetch returning {description, source_reference, title}."""
    if do_dcid in cache:
        return cache[do_dcid]
    _ensure()
    try:
        resp = call_tool(
            "get_design_control",
            {"dc_type": "design-output", "dc_id": do_dcid},
        )
    except Exception as exc:
        print(f"    ! DO fetch failed for {do_dcid}: {exc}",
              file=sys.stderr)
        cache[do_dcid] = {"description": "", "source_reference": "",
                          "title": ""}
        return cache[do_dcid]
    do = resp.get("designOutput") or resp.get("design_output") or {}
    cache[do_dcid] = {
        "description": do.get("description", "") or "",
        "source_reference": (do.get("source_reference")
                             or do.get("sourceReference") or ""),
        "title": do.get("title", "") or "",
    }
    return cache[do_dcid]


def collect_paths(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in PATH_RE.finditer(text):
        p = m.group(1).rstrip(".,;")
        if p not in out:
            out.append(p)
    return out


def infer_framework(path: str) -> str:
    p = path.lower()
    if p.endswith(".py"):
        return "pytest"
    if p.endswith(".spec.ts") or p.endswith(".spec.tsx") or "/e2e/" in p:
        return "playwright"
    if p.endswith((".test.ts", ".test.tsx", ".test.js", ".test.jsx")):
        return "jest"
    if p.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "jest"
    return "unknown"


def is_test_path(p: str) -> bool:
    pl = p.lower()
    return (
        "/tests/" in pl
        or "__tests__" in pl
        or pl.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts",
                        ".spec.tsx"))
        or "/e2e/" in pl
        or pl.startswith("tests/")
    )


def vt_paths_and_framework(do_blobs: list[dict],
                           vt_desc: str | None) -> tuple[str, str, str]:
    """Returns (test_file_path, framework, automation_status)."""
    candidates: list[str] = []
    for do in do_blobs:
        candidates.extend(collect_paths(do.get("source_reference")))
        candidates.extend(collect_paths(do.get("description")))
        candidates.extend(collect_paths(do.get("title")))
    candidates.extend(collect_paths(vt_desc))

    seen: list[str] = []
    for p in candidates:
        if p not in seen:
            seen.append(p)

    if not seen:
        return "", "unknown", "manual"
    test_paths = [p for p in seen if is_test_path(p)]
    chosen = test_paths[0] if test_paths else seen[0]
    framework = infer_framework(chosen)
    automation = "automated" if test_paths else "manual"
    return chosen, framework, automation


def vt_status_norm(node: dict) -> str:
    raw = (node.get("executionStatus") or node.get("execution_status")
           or "").lower()
    if raw == "passed":
        return "passed"
    if raw == "failed":
        return "failed"
    return "not_executed"


def classify_release(un_node: dict, di_nodes_for_un: list[dict]) -> str | None:
    dcid = un_node["dcId"]
    if dcid in R1_UNS:
        return "R1"
    if dcid == R7_ANCHOR_UN:
        return "R7"
    if any(di["dcId"] in R7_WIDGET_DIS for di in di_nodes_for_un):
        return "R7"
    haystack = (
        (un_node.get("title") or "") + " "
        + (un_node.get("description") or "") + " "
        + " ".join((di.get("title") or "") + " "
                   + (di.get("description") or "")
                   for di in di_nodes_for_un)
    ).lower()
    for release in ("R3", "R4", "R5", "R7"):
        for kw in KEYWORDS[release]:
            if kw in haystack:
                return release
    return None


def build() -> tuple[list[dict], list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-cache-matrix", action="store_true")
    parser.add_argument("--skip-do-fetch", action="store_true",
                        help="Skip per-DO source_reference fetches; "
                             "rely on cached entries + matrix descriptions. "
                             "Useful when Atlas DO fetches are flaky.")
    args = parser.parse_args()

    matrix = fetch_matrix(use_cache=not args.no_cache_matrix)
    nodes = matrix["nodes"]
    links = matrix["links"]
    rows_in = matrix["rows"]

    by_uuid = {n["id"]: n for n in nodes}
    do_cache: dict = {}
    if DO_CACHE.exists():
        do_cache = json.loads(DO_CACHE.read_text())

    rel_assignments: dict[str, str] = {}
    not_found: list[str] = []
    for un_dcid in R1_UNS:
        rel_assignments[un_dcid] = "R1"

    out_rows: list[dict] = []
    print("\nstep 1: classifying UNs ...")
    seen_uns_in_matrix: set[str] = set()
    for row in rows_in:
        un = row["userNeed"]
        seen_uns_in_matrix.add(un["dcId"])
        di_nodes = row.get("designInputs", []) or []
        rel = classify_release(un, di_nodes)
        if rel is None:
            continue
        rel_assignments.setdefault(un["dcId"], rel)

    for un_dcid in R1_UNS:
        if un_dcid not in seen_uns_in_matrix:
            not_found.append(un_dcid)

    print(f"  classified {len(rel_assignments)} UNs across releases")

    print("\nstep 2: walking links to build VT rows ...")
    by_release_uns: dict[str, set[str]] = {}
    for un_dcid, rel in rel_assignments.items():
        by_release_uns.setdefault(rel, set()).add(un_dcid)
    for rel in sorted(by_release_uns):
        print(f"  {rel}: {len(by_release_uns[rel])} UNs in scope")

    do_dcids_needed: set[str] = set()
    for row in rows_in:
        un_dcid = row["userNeed"]["dcId"]
        rel = rel_assignments.get(un_dcid)
        if rel is None:
            continue
        for do in row.get("designOutputs", []) or []:
            do_dcids_needed.add(do["dcId"])

    fresh = [d for d in do_dcids_needed if d not in do_cache]
    if fresh and not args.skip_do_fetch:
        print(f"\nstep 3: fetching {len(fresh)} DO source_refs (one-off, "
              "cached for future runs) ...")
        for i, dcid in enumerate(sorted(fresh), 1):
            fetch_do_source_ref(dcid, do_cache)
            if i % 10 == 0:
                print(f"    ... {i}/{len(fresh)}")
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                DO_CACHE.write_text(json.dumps(do_cache, indent=2))
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        DO_CACHE.write_text(json.dumps(do_cache, indent=2))
    elif fresh:
        print(f"\nstep 3: SKIPPED ({len(fresh)} DOs would need fetching). "
              "Path inference uses cached entries + matrix descriptions only.")

    print("\nstep 4: emitting rows ...")
    for row in rows_in:
        un_dcid = row["userNeed"]["dcId"]
        rel = rel_assignments.get(un_dcid)
        if rel is None:
            continue
        di_nodes = row.get("designInputs", []) or []
        di_uuid_to_dcid = {di["id"]: di["dcId"] for di in di_nodes}
        do_nodes = row.get("designOutputs", []) or []
        vt_nodes = row.get("verificationTests", []) or []
        vt_by_uuid = {vt["id"]: vt for vt in vt_nodes}

        do_uuid_to_dis: dict[str, list[str]] = {do["id"]: []
                                                for do in do_nodes}
        vt_to_dis: dict[str, list[str]] = {vt["id"]: [] for vt in vt_nodes}
        for ln in links:
            if ln.get("relationship") == "IMPLEMENTS":
                if ln["source"] in do_uuid_to_dis and \
                        ln["target"] in di_uuid_to_dcid:
                    do_uuid_to_dis[ln["source"]].append(
                        di_uuid_to_dcid[ln["target"]])
            elif ln.get("relationship") == "VERIFIES":
                if ln["source"] in vt_to_dis and \
                        ln["target"] in di_uuid_to_dcid:
                    vt_to_dis[ln["source"]].append(
                        di_uuid_to_dcid[ln["target"]])

        di_to_dos: dict[str, list[dict]] = {dcid: [] for dcid
                                            in di_uuid_to_dcid.values()}
        for do in do_nodes:
            for di_dcid in do_uuid_to_dis.get(do["id"], []):
                blob = do_cache.get(do["dcId"]) or {
                    "description": do.get("description", ""),
                    "source_reference": "",
                    "title": do.get("title", ""),
                }
                di_to_dos[di_dcid].append(blob)

        for vt_uuid, di_dcids in vt_to_dis.items():
            vt_node = vt_by_uuid.get(vt_uuid)
            if vt_node is None:
                continue
            if not di_dcids:
                di_dcids = [""]
            for di_dcid in di_dcids:
                test_path, framework, automation = vt_paths_and_framework(
                    di_to_dos.get(di_dcid, []),
                    vt_node.get("description", ""),
                )
                on_disk = bool(test_path) and (ROOT / test_path).exists()
                out_rows.append({
                    "vt_dcid": vt_node["dcId"],
                    "di_dcid": di_dcid,
                    "un_dcid": un_dcid,
                    "release": rel,
                    "framework": framework,
                    "automation_status": automation,
                    "test_file_path": test_path,
                    "on_disk": str(on_disk).lower(),
                    "current_status": vt_status_norm(vt_node),
                    "owner": "",
                    "run_started_at": "",
                    "run_finished_at": "",
                    "run_result": "",
                    "run_log_path": "",
                    "atlas_updated_at": "",
                    "vt_uuid": vt_node["id"],
                    "vt_title": (vt_node.get("title") or "")[:200],
                })

    out_rows = dedupe_rows(out_rows)
    out_rows.sort(key=lambda r: (RELEASE_ORDER.index(r["release"]),
                                 r["un_dcid"], r["di_dcid"], r["vt_dcid"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, lineterminator="\n")
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"\nwrote {len(out_rows)} rows to {args.out}")
    return out_rows, not_found


def dedupe_rows(rows: list[dict]) -> list[dict]:
    """One row per (vt_dcid, di_dcid). First-wins (release priority)."""
    seen: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["vt_dcid"], r["di_dcid"])
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def report(rows: list[dict], not_found: list[str]) -> None:
    """Per-release breakdown.

    Reports both ROW counts (one row per VT/DI link) and DISTINCT VT
    counts. The brief asks for VT counts, but the CSV is one row per
    (VT, DI) tuple so the same VT can appear multiple times.
    """
    print("\n=== per-release counts ===")
    by_release: dict[str, set] = {}
    by_rel_status: dict[tuple[str, str], set] = {}
    by_rel_fw: dict[tuple[str, str], set] = {}
    by_rel_disk: dict[tuple[str, bool], set] = {}
    by_rel_auto: dict[tuple[str, str], set] = {}
    for r in rows:
        rel = r["release"]
        vt = r["vt_dcid"]
        by_release.setdefault(rel, set()).add(vt)
        by_rel_status.setdefault((rel, r["current_status"]), set()).add(vt)
        by_rel_fw.setdefault((rel, r["framework"]), set()).add(vt)
        by_rel_disk.setdefault((rel, r["on_disk"] == "true"), set()).add(vt)
        by_rel_auto.setdefault((rel, r["automation_status"]), set()).add(vt)
    total_distinct = len({r["vt_dcid"] for r in rows})
    total_not_exec = len({r["vt_dcid"] for r in rows
                          if r["current_status"] == "not_executed"})
    total_passed = len({r["vt_dcid"] for r in rows
                        if r["current_status"] == "passed"})

    for rel in RELEASE_ORDER:
        if rel not in by_release:
            continue
        n = len(by_release[rel])
        print(f"  {rel}: {n} distinct VTs")
        for status in ("not_executed", "passed", "failed"):
            v = len(by_rel_status.get((rel, status), set()))
            if v:
                print(f"    status={status}: {v}")
        for fw in ("pytest", "jest", "playwright", "unknown"):
            v = len(by_rel_fw.get((rel, fw), set()))
            if v:
                print(f"    framework={fw}: {v}")
        for au in ("automated", "manual"):
            v = len(by_rel_auto.get((rel, au), set()))
            if v:
                print(f"    automation={au}: {v}")
        on = len(by_rel_disk.get((rel, True), set()))
        off = len(by_rel_disk.get((rel, False), set()))
        print(f"    on_disk=true: {on}    on_disk=false (paper): {off}")
    print(f"\n  TOTAL distinct MVP-scope VTs: {total_distinct}")
    print(f"  TOTAL passed:                 {total_passed}")
    print(f"  TOTAL not_executed:           {total_not_exec}")
    print(f"  TOTAL CSV rows (VT/DI links): {len(rows)}")
    if not_found:
        print("\n=== UNs from R1 brief that are NOT in Atlas ===")
        for u in sorted(not_found):
            print(f"  {u}")


def main() -> int:
    rows, not_found = build()
    report(rows, not_found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
