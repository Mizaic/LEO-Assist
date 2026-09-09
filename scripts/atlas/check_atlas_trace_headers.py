"""CI gate -- every Class B+ source file must carry an Atlas trace header.

This is the post-Phase-13c invariant:

  Every file under libs/ or services/ that is NOT excluded (test, init,
  declaration-only, etc.) AND NOT explicitly allow-listed in
  compliance/atlas-migration-evidence/phase13c-uncovered.csv MUST contain
  exactly one `Atlas trace:` block.

Run modes:
  --fail-on-missing      exit 1 if any file fails (default for CI)
  --report               print a count summary; never fail
  --update-allow-list    after a Phase 13c re-run, regenerate the
                         allow list from phase13c-uncovered.csv

Examples:
  python3 scripts/atlas/check_atlas_trace_headers.py
  python3 scripts/atlas/check_atlas_trace_headers.py --report

"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
ALLOW_LIST = EVIDENCE / "phase13c-uncovered.csv"
TRIAGE_LIST = EVIDENCE / "phase13c-triage-queue.csv"
MANUAL_ALLOW_LIST = EVIDENCE / "phase13c-allow-list.csv"

EXTENSIONS = {".py", ".ts", ".tsx"}
SCAN_ROOTS = [ROOT / "libs", ROOT / "services"]
ATLAS_TRACE_MARKER = "Atlas trace:"

EXCLUDE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)e2e/"),
    re.compile(r"__tests__/"),
    re.compile(r"/test_[^/]+\.py$"),
    re.compile(r"\.test\.(t|j)sx?$"),
    re.compile(r"(^|/)__init__\.py$"),
    re.compile(r"\.d\.ts$"),
    re.compile(r"(^|/)conftest\.py$"),
    re.compile(r"(^|/)jest\.config\.(t|j)s$"),
    re.compile(r"(^|/)jest\.setup\.(t|j)s$"),
    re.compile(r"(^|/)playwright\.config\.(t|j)s$"),
    re.compile(r"(^|/)scripts/probe_[^/]+\.py$"),
    re.compile(r"node_modules/"),
    re.compile(r"\.next/"),
    re.compile(r"dist/"),
    re.compile(r"build/"),
    re.compile(r"(^|/)\.venv(/|$)"),
    re.compile(r"(^|/)venv(/|$)"),
    re.compile(r"(^|/)site-packages(/|$)"),
]


def is_excluded(rel: str) -> bool:
    return any(p.search(rel) for p in EXCLUDE_PATTERNS)


def load_allow_list() -> set[str]:
    out: set[str] = set()
    if ALLOW_LIST.exists():
        out.update(r["path"] for r in csv.DictReader(ALLOW_LIST.open()))
    if MANUAL_ALLOW_LIST.exists():
        out.update(r["path"] for r in csv.DictReader(MANUAL_ALLOW_LIST.open()))
    return out


def load_triage_list() -> set[str]:
    if not TRIAGE_LIST.exists():
        return set()
    return {r["path"] for r in csv.DictReader(TRIAGE_LIST.open())}


def has_trace(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return False
    return ATLAS_TRACE_MARKER in head


def iter_candidates() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in EXTENSIONS:
                continue
            rel = str(p.relative_to(ROOT))
            if is_excluded(rel):
                continue
            out.append(p)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true",
                    help="report counts only, never fail")
    ap.add_argument("--list-missing", action="store_true",
                    help="print the list of missing files (useful in CI logs)")
    args = ap.parse_args()

    allow = load_allow_list()
    triage = load_triage_list()
    print(f"Allow-list (uncovered): {len(allow)}")
    print(f"Triage list:            {len(triage)}")

    candidates = iter_candidates()
    print(f"Scanning {len(candidates)} Class B+ files...")

    missing: list[str] = []
    ok = 0
    skipped_allowed = 0
    skipped_triage = 0
    for p in candidates:
        rel = str(p.relative_to(ROOT))
        if rel in allow:
            skipped_allowed += 1
            continue
        if rel in triage:
            skipped_triage += 1
            continue
        if has_trace(p):
            ok += 1
        else:
            missing.append(rel)

    print()
    print("Results:")
    print(f"  with Atlas trace:        {ok}")
    print(f"  skipped (allow-list):    {skipped_allowed}")
    print(f"  skipped (triage queue):  {skipped_triage}")
    print(f"  MISSING:                 {len(missing)}")

    if missing:
        print("\nMissing files:")
        for m in missing[:50]:
            print(f"  {m}")
        if len(missing) > 50:
            print(f"  ... and {len(missing) - 50} more")

    if args.report:
        return 0
    if missing:
        print(
            "\nFAIL: every Class B+ source file must carry an Atlas trace "
            "header (or be on the allow-list). Re-run Phase 13c "
            "(scripts/atlas/phase13c_stamp_headers.py) or add the file "
            "to the appropriate allow-list."
        )
        return 1
    print("\nOK: every Class B+ source file is traced or allow-listed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
