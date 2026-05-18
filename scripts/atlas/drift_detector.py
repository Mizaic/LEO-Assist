"""Drift detector -- keep Atlas DO source_reference in sync with in-file
Atlas trace headers.

What it checks (read-only):

  1. Forward drift  (file -> Atlas):
     For every Class B+ file with an `Atlas trace:` header, parse the
     `DO:` (and `Also implements:`) lines. For each named DO, fetch
     `get_design_control(dc_id=..., dc_type="design-output")` and check
     that `source_reference` lists the file path. Flag any miss.

  2. Reverse drift  (Atlas -> file):
     For every Atlas DO with a `source_reference`, parse the path list.
     For each path, check the file exists on disk AND its trace header
     names this DO. Flag any miss.

  3. Stale tag drift:
     Atlas DOs whose `source_reference` still ends with `[phase13b]`
     are reconstructions; flag them so dev work can drop the tag once
     the value has been kept fresh.

  4. Header invariant:
     Files with multiple `Atlas trace:` blocks, files whose `DO:`
     value does not parse as `DO-XXXXXXXX`, files whose `DO:` is not
     a real Atlas dcId.

Outputs (under compliance/atlas-migration-evidence/drift/<UTC date>/):

  - drift-forward.csv     # file says X, Atlas does not list file
  - drift-reverse.csv     # Atlas lists file, file does not say X
  - drift-stale-tag.csv   # source_reference still has [phase13b]
  - drift-header-invariant.csv
  - drift-summary.md      # human-readable rollup

Usage:

  python3 scripts/atlas/drift_detector.py            # full check, exit non-zero on drift
  python3 scripts/atlas/drift_detector.py --report   # never fail; report-only mode
  python3 scripts/atlas/drift_detector.py --fast     # skip the per-DO Atlas fetch and use the cached snapshot

The --fast mode reads the Phase 13c cache. The default mode refreshes
every DO via Atlas; budget ~30 minutes for the full run.
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
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import McpError, call_tool, initialize  # noqa: E402

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
DRIFT_DIR = EVIDENCE / "drift"
CACHE_JSON = EVIDENCE / "phase13c-atlas-cache.json"
ALLOW_LIST = EVIDENCE / "phase13c-uncovered.csv"
TRIAGE_LIST = EVIDENCE / "phase13c-triage-queue.csv"
MANUAL_ALLOW_LIST = EVIDENCE / "phase13c-allow-list.csv"

EXTENSIONS = {".py", ".ts", ".tsx"}
SCAN_ROOTS = [ROOT / "libs", ROOT / "services"]
ATLAS_TRACE_MARKER = "Atlas trace:"
DCID_RE = re.compile(r"\b(DO|DI|UN|VT|VAL|R)-([0-9A-Fa-f]{8})\b")
DO_LINE_RE = re.compile(r"^\s*\*?\s*DO:\s*(DO-[0-9A-Fa-f]{8})\s*$",
                        re.IGNORECASE | re.MULTILINE)
ALSO_LINE_RE = re.compile(
    r"^\s*\*?\s*Also implements:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
EXCLUDE_PATTERNS = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)e2e/"),
    re.compile(r"__tests__/"),
    re.compile(r"/test_[^/]+\.py$"),
    re.compile(r"\.test\.(t|j)sx?$"),
    re.compile(r"(^|/)__init__\.py$"),
    re.compile(r"\.d\.ts$"),
    re.compile(r"(^|/)conftest\.py$"),
    re.compile(r"node_modules/"),
    re.compile(r"\.next/"),
    re.compile(r"dist/"),
    re.compile(r"build/"),
]


# ----------------------------------------------------------------------
# IO helpers
# ----------------------------------------------------------------------

def is_excluded(rel: str) -> bool:
    return any(p.search(rel) for p in EXCLUDE_PATTERNS)


def load_skip_set() -> set[str]:
    out: set[str] = set()
    for p in (ALLOW_LIST, TRIAGE_LIST, MANUAL_ALLOW_LIST):
        if p.exists():
            out.update(r["path"] for r in csv.DictReader(p.open()))
    return out


def iter_candidates() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in EXTENSIONS:
                continue
            if is_excluded(str(p.relative_to(ROOT))):
                continue
            out.append(p)
    return sorted(out)


def parse_trace_block(text: str) -> tuple[str, list[str]]:
    """Return (primary_do, [also_implements_dos]). Empty if no block."""
    if ATLAS_TRACE_MARKER not in text[:8000]:
        return "", []
    head = text[:8000]
    m = DO_LINE_RE.search(head)
    if not m:
        return "", []
    primary = m.group(1).upper().replace("DO-", "DO-")
    primary = "DO-" + primary[3:].upper()
    extras: list[str] = []
    am = ALSO_LINE_RE.search(head)
    if am:
        body = am.group(1)
        for hit in re.findall(r"DO-[0-9A-Fa-f]{8}", body):
            extras.append("DO-" + hit[3:].upper())
    return primary, extras


def count_trace_blocks(text: str) -> int:
    return len(re.findall(re.escape(ATLAS_TRACE_MARKER), text[:8000]))


# ----------------------------------------------------------------------
# Atlas DO fetch
# ----------------------------------------------------------------------

def fetch_do(dc_id: str) -> dict | None:
    try:
        out = call_tool(
            "get_design_control",
            {"dc_id": dc_id, "dc_type": "design-output"},
        )
    except McpError as e:
        print(f"  ! {dc_id}: {e}")
        return None
    do = out.get("designOutput", {}) or {}
    return {
        "dcId": dc_id,
        "title": do.get("title", ""),
        "source_reference": (
            do.get("source_reference")
            or do.get("sourceReference")
            or ""
        ),
    }


def list_atlas_dos() -> list[str]:
    """Return all DO dcIds known to Atlas via the live matrix."""
    matrix = call_tool(
        "get_traceability_matrix", {"product_id": "PROD-LEO-CORE-AI-20260415-6AE8A23B"}
    )
    seen: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            d = node.get("dcId") or node.get("dc_id")
            if (
                isinstance(d, str)
                and d.startswith("DO-")
                and len(d) <= 16
            ):
                seen.add(d)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(matrix)
    return sorted(seen)


# ----------------------------------------------------------------------
# Drift checks
# ----------------------------------------------------------------------

def parse_source_reference(value: str) -> tuple[list[str], bool]:
    """Return (paths, has_phase13b_tag)."""
    has_tag = value.endswith("[phase13b]") or "[phase13b]" in value
    body = value.replace("[phase13b]", "").strip()
    paths = sorted({p.strip() for p in body.split(";") if p.strip()})
    return paths, has_tag


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true",
                    help="report-only mode (never fail)")
    ap.add_argument("--fast", action="store_true",
                    help="use phase13c-atlas-cache.json instead of fetching live")
    ap.add_argument("--limit-dos", type=int, default=0,
                    help="limit the number of DOs we re-fetch (debug)")
    ap.add_argument(
        "--dos-from-bucket-ids", action="store_true",
        help="restrict scan to DOs in phase14d-bucket-ids.json + DOs "
             "named in any file header (avoids the slow full-Atlas "
             "list_dos call)",
    )
    args = ap.parse_args()

    if not args.fast:
        initialize()

    skip = load_skip_set()
    candidates = iter_candidates()
    print(f"Scanning {len(candidates)} Class B+ files (skip set: {len(skip)})")

    # ----- Pass 1: walk files, build file -> [primary_do, *extras] -----
    file_to_dos: dict[str, list[str]] = {}
    multi_block: list[str] = []
    bad_do: list[str] = []
    no_block_but_required: list[str] = []
    for p in candidates:
        rel = str(p.relative_to(ROOT))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = count_trace_blocks(text)
        if n == 0:
            if rel not in skip:
                no_block_but_required.append(rel)
            continue
        if n > 1:
            multi_block.append(rel)
        primary, extras = parse_trace_block(text)
        if not primary:
            bad_do.append(rel)
            continue
        file_to_dos[rel] = [primary] + extras

    print(
        f"  files with header: {len(file_to_dos)}; "
        f"multi-block: {len(multi_block)}; "
        f"unparseable DO: {len(bad_do)}; "
        f"missing block (not allow-listed): {len(no_block_but_required)}"
    )

    # ----- Pass 2: for every DO either named in a header OR live in Atlas, fetch source_reference -----
    do_data: dict[str, dict] = {}
    if args.fast:
        if not CACHE_JSON.exists():
            print("ERROR: --fast requires phase13c-atlas-cache.json", file=sys.stderr)
            return 2
        cache = json.loads(CACHE_JSON.read_text())
        # Cache does not have source_reference; fall back to fetch for those.
        print("WARNING: --fast cache lacks source_reference; "
              "doing per-DO fetch only for header-named DOs.")
        targets = set()
        for dos in file_to_dos.values():
            targets.update(dos)
        targets = sorted(targets)
        if args.limit_dos:
            targets = targets[: args.limit_dos]
        initialize()
        for i, d in enumerate(targets, 1):
            rec = fetch_do(d)
            if rec is not None:
                do_data[d] = rec
            if i % 20 == 0:
                print(f"  ... fetched {i}/{len(targets)}")
    else:
        if args.dos_from_bucket_ids:
            bid_path = (
                ROOT / "compliance" / "atlas-migration-evidence"
                / "phase14d-bucket-ids.json"
            )
            bucket_dos: set[str] = set()
            if bid_path.exists():
                bj = json.loads(bid_path.read_text())
                for v in bj.values():
                    d = v.get("do") or ""
                    if d and not d.startswith("DO-"):
                        d = f"DO-{d}"
                    if d:
                        bucket_dos.add(d)
            all_dos = sorted(bucket_dos)
            print(f"  scoped to {len(all_dos)} bucket DOs from "
                  f"phase14d-bucket-ids.json")
        else:
            all_dos = list_atlas_dos()
        targets = sorted(set(all_dos) | {d for ds in file_to_dos.values() for d in ds})
        if args.limit_dos:
            targets = targets[: args.limit_dos]
        print(f"  fetching source_reference for {len(targets)} DOs from Atlas...")
        for i, d in enumerate(targets, 1):
            rec = fetch_do(d)
            if rec is not None:
                do_data[d] = rec
            if i % 20 == 0:
                print(f"  ... fetched {i}/{len(targets)}")

    # ----- Pass 3: compute drifts -----
    forward: list[dict] = []     # file -> dco missing the file
    reverse: list[dict] = []     # Atlas -> file missing or wrong header
    stale_tag: list[dict] = []
    header_inv: list[dict] = []

    for d, rec in do_data.items():
        paths, tag = parse_source_reference(rec["source_reference"])
        if tag:
            stale_tag.append({
                "dc_id": d,
                "title": rec["title"],
                "n_paths": str(len(paths)),
            })
        for path in paths:
            full = ROOT / path
            if not full.exists():
                reverse.append({
                    "dc_id": d,
                    "path": path,
                    "category": "missing-file",
                    "note": "source_reference lists a file that no longer exists",
                })
                continue
            if is_excluded(path):
                continue
            try:
                txt = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            primary, extras = parse_trace_block(txt)
            if not primary:
                reverse.append({
                    "dc_id": d,
                    "path": path,
                    "category": "missing-header",
                    "note": "Atlas DO lists this file but file has no Atlas trace block",
                })
                continue
            if d != primary and d not in extras:
                reverse.append({
                    "dc_id": d,
                    "path": path,
                    "category": "header-points-elsewhere",
                    "note": (
                        f"file header points at {primary}, "
                        f"not {d} (this DO claims it via source_reference)"
                    ),
                })

    for rel, dos in file_to_dos.items():
        for d in dos:
            rec = do_data.get(d)
            if rec is None:
                continue
            paths, _ = parse_source_reference(rec["source_reference"])
            if rel not in paths:
                forward.append({
                    "path": rel,
                    "dc_id": d,
                    "note": (
                        "file header names this DO but DO source_reference "
                        "does not list the file"
                    ),
                })

    for rel in multi_block:
        header_inv.append({
            "path": rel,
            "category": "multiple-blocks",
            "note": "more than one 'Atlas trace:' marker in the file",
        })
    for rel in bad_do:
        header_inv.append({
            "path": rel,
            "category": "unparseable-do",
            "note": "Atlas trace block but no parseable 'DO:' line",
        })

    # ----- Write outputs -----
    today = time.strftime("%Y-%m-%d", time.gmtime())
    out_dir = DRIFT_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    def write(name: str, cols: list[str], rows: list[dict]) -> Path:
        p = out_dir / name
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        return p

    fwd_path = write("drift-forward.csv", ["path", "dc_id", "note"], forward)
    rev_path = write(
        "drift-reverse.csv", ["dc_id", "path", "category", "note"], reverse
    )
    stale_path = write(
        "drift-stale-tag.csv", ["dc_id", "title", "n_paths"], stale_tag
    )
    inv_path = write(
        "drift-header-invariant.csv", ["path", "category", "note"], header_inv
    )

    summary = out_dir / "drift-summary.md"
    summary.write_text(
        f"# Drift report -- {today}\n\n"
        f"- Files with Atlas trace header: {len(file_to_dos)}\n"
        f"- Atlas DOs probed: {len(do_data)}\n"
        f"- Forward drift (file -> Atlas): **{len(forward)}**\n"
        f"- Reverse drift (Atlas -> file): **{len(reverse)}**\n"
        f"- Stale [phase13b] tags:        **{len(stale_tag)}**\n"
        f"- Header invariant breaches:    **{len(header_inv)}**\n"
        f"\n## Outputs\n\n"
        f"- {fwd_path.relative_to(ROOT)}\n"
        f"- {rev_path.relative_to(ROOT)}\n"
        f"- {stale_path.relative_to(ROOT)}\n"
        f"- {inv_path.relative_to(ROOT)}\n"
    )
    print(f"\nDrift report:")
    print(f"  forward:  {len(forward)}")
    print(f"  reverse:  {len(reverse)}")
    print(f"  stale:    {len(stale_tag)}")
    print(f"  invariant:{len(header_inv)}")
    print(f"  summary:  {summary}")

    fail = (
        len(forward) > 0
        or len(reverse) > 0
        or len(header_inv) > 0
    )
    if args.report or not fail:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
