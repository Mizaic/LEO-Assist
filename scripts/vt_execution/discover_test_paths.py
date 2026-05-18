"""Map source modules in the backlog to their real test files.

Wave-2 surfaced a path-inference bug: many DOs referenced only the
source module (e.g. `libs/nlp/sentence_splitter.py`) and the backlog
builder used that as the test_file_path. pytest collected zero tests
and recorded a false-fail.

This helper rewrites rows where `current_status == "needs_test_path"`,
substituting the inferred source module path with a real test file
and flipping the row back to automated.

Strategy:
  1. Strip directory; keep stem (e.g. `sentence_splitter`).
  2. Search canonical test directories for `test_<stem>.py` and
     `<stem>_test.py`. Use Glob-like rglob.
  3. Prefer test files whose path overlaps with the original module
     (e.g. matching `services/api` -> `services/api/tests/`).
  4. If exactly one match -> rewrite the row, mark automated.
  5. If 0 or >1 matches -> leave row marked needs_test_path with a
     "candidates" hint in run_log_path for human triage.

ASCII only. Tooling, not under design control.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "scripts" / "vt_execution" / "mvp_vt_backlog.csv"
TEST_DIRS = [ROOT / "tests", ROOT / "services", ROOT / "libs"]


def _candidate_names(stem: str) -> list[str]:
    return [f"test_{stem}.py", f"{stem}_test.py"]


def _score_overlap(orig: str, candidate: Path) -> int:
    """Higher is better. Counts shared path segments."""
    rel = candidate.relative_to(ROOT).as_posix()
    a = orig.split("/")
    b = rel.split("/")
    shared = 0
    for x, y in zip(a, b):
        if x == y:
            shared += 1
        else:
            break
    return shared


def discover(orig_path: str) -> tuple[str, list[str]]:
    """Return (best_match_or_empty, all_candidates_relative)."""
    p = Path(orig_path)
    stem = p.stem
    if stem.startswith("test_") or stem.endswith("_test"):
        return orig_path, []
    names = _candidate_names(stem)
    matches: list[Path] = []
    for d in TEST_DIRS:
        if not d.exists():
            continue
        for name in names:
            for hit in d.rglob(name):
                if hit not in matches:
                    matches.append(hit)
    if not matches:
        return "", []
    if len(matches) == 1:
        return matches[0].relative_to(ROOT).as_posix(), []
    matches.sort(key=lambda m: -_score_overlap(orig_path, m))
    best = matches[0]
    rels = [m.relative_to(ROOT).as_posix() for m in matches]
    if _score_overlap(orig_path, best) >= 2:
        return best.relative_to(ROOT).as_posix(), rels
    return "", rels


def rewrite_backlog(dry_run: bool) -> int:
    rows = list(csv.DictReader(open(BACKLOG)))
    fields = list(rows[0].keys())
    rewritten = 0
    ambiguous = 0
    nothing = 0
    seen_vt: dict[str, str] = {}
    for r in rows:
        if r["current_status"] != "needs_test_path":
            continue
        vt = r["vt_dcid"]
        if vt in seen_vt:
            r["test_file_path"] = seen_vt[vt]
            if seen_vt[vt]:
                r["automation_status"] = "automated"
                r["current_status"] = "not_executed"
                r["run_result"] = ""
            continue
        new_path, candidates = discover(r["test_file_path"])
        if new_path:
            r["test_file_path"] = new_path
            r["on_disk"] = "true"
            r["automation_status"] = "automated"
            r["current_status"] = "not_executed"
            r["run_result"] = ""
            rewritten += 1
        elif candidates:
            r["run_log_path"] = "candidates: " + ", ".join(candidates[:3])
            ambiguous += 1
        else:
            nothing += 1
        seen_vt[vt] = new_path
    if not dry_run:
        with open(BACKLOG, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print(f"rewritten distinct VTs: {rewritten}")
    print(f"ambiguous (multi-candidate, kept manual): {ambiguous}")
    print(f"no candidate found (kept manual): {nothing}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return rewrite_backlog(args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
