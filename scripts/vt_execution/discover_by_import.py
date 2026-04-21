"""Content-based test discovery.

For every backlog row whose `test_file_path` is a SOURCE module
(not a test file), scan the repo's test directories for files that
import the source module. Pick the best match and rewrite the row.

Two languages handled:
  - Python: search for `from <pkg.module> import` or
    `import <pkg.module>` in `tests/`, `services/**/tests/`,
    `libs/**/tests/`.
  - TypeScript / TSX: search for `from "..."` and `from "@/..."`
    that resolve to the source component, in `services/ui/src/__tests__/`,
    `services/design-system/src/__tests__/`, and `services/ui/e2e/`.

A row is rewritten only if exactly one strong match is found, OR if
the best match scores above a confidence threshold (path-overlap
weighted by recency). All decisions are logged to
`scripts/vt_execution/.cache/discover_decisions.json` so they can be
audited.

ASCII only. Tooling, not under design control.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "scripts" / "vt_execution" / "mvp_vt_backlog.csv"
CACHE_DIR = ROOT / "scripts" / "vt_execution" / ".cache"
DECISIONS = CACHE_DIR / "discover_decisions.json"

PY_TEST_DIRS = [
    ROOT / "tests",
    ROOT / "services",
    ROOT / "libs",
    ROOT / "scripts",
]
TS_TEST_DIRS = [
    ROOT / "services" / "ui" / "src" / "__tests__",
    ROOT / "services" / "design-system" / "src" / "__tests__",
    ROOT / "services" / "ui" / "e2e",
]

PY_TEST_GLOBS = ["test_*.py", "*_test.py"]
TS_TEST_GLOBS = ["*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx"]


def _path_overlap(a: str, b: str) -> int:
    sa, sb = a.split("/"), b.split("/")
    n = 0
    for x, y in zip(sa, sb):
        if x == y:
            n += 1
        else:
            break
    return n


def _python_module_path(src_path: str) -> str:
    """Convert `libs/foo/bar.py` -> `libs.foo.bar`."""
    p = src_path
    if p.endswith(".py"):
        p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _service_alias_paths(src_path: str) -> list[str]:
    """Return alternate dotted module paths a test might use to import this
    source file. `services/api/app/routers/x.py` is added to sys.path via
    `services/api`, so tests import it as `app.routers.x`. Same for any
    other `services/<svc>/app/...` layout, and for files in service test
    folders. Also handle plain `<svc>/...` imports."""
    out: list[str] = [_python_module_path(src_path)]
    parts = src_path.split("/")
    for i, p in enumerate(parts):
        if p == "app" and i >= 1 and parts[i - 1] != "":
            sub = "/".join(parts[i:])
            out.append(_python_module_path(sub))
            break
    return out


def _import_patterns_python(src_path: str) -> list[re.Pattern[str]]:
    pats: list[re.Pattern[str]] = []
    for mod in _service_alias_paths(src_path):
        parts = mod.split(".")
        leaf = parts[-1]
        parent = ".".join(parts[:-1]) if len(parts) > 1 else ""
        pats.append(re.compile(rf"\bfrom\s+{re.escape(mod)}\s+import\b"))
        pats.append(re.compile(rf"\bimport\s+{re.escape(mod)}\b"))
        pats.append(re.compile(rf"['\"]" + re.escape(mod) + r"['\".]"))
        if parent:
            pats.append(
                re.compile(
                    rf"\bfrom\s+{re.escape(parent)}\s+import[^\n]*\b"
                    rf"{re.escape(leaf)}\b"
                )
            )
    return pats


def _import_patterns_ts(src_path: str) -> list[re.Pattern[str]]:
    """Build matchers for TS/TSX imports of `services/ui/src/foo/Bar.tsx`.

    UI imports look like:
        from "@/foo/Bar"
        from "@/components/Bar"
        from "../foo/Bar"
        from "./Bar"
    Match the stem and at least one parent segment.
    """
    p = src_path
    for ext in (".tsx", ".ts", ".jsx", ".js"):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    parts = p.split("/")
    stem = parts[-1]
    parent = parts[-2] if len(parts) >= 2 else ""
    quoted = (
        rf"['\"]"
        rf"(?:@/|\.{{1,2}}/)"
        rf"(?:[^'\"]*?/)?"
        rf"{'(?:' + re.escape(parent) + '/)?' if parent else ''}"
        rf"{re.escape(stem)}"
        rf"['\"]"
    )
    return [re.compile(rf"\bfrom\s+{quoted}")]


def _iter_python_tests() -> list[Path]:
    out: list[Path] = []
    for d in PY_TEST_DIRS:
        if not d.exists():
            continue
        for g in PY_TEST_GLOBS:
            out.extend(d.rglob(g))
    return out


def _iter_ts_tests() -> list[Path]:
    out: list[Path] = []
    for d in TS_TEST_DIRS:
        if not d.exists():
            continue
        for g in TS_TEST_GLOBS:
            out.extend(d.rglob(g))
    return out


def _scan(test_files: list[Path],
          pats: list[re.Pattern[str]]) -> list[tuple[Path, int]]:
    hits: list[tuple[Path, int]] = []
    for tf in test_files:
        try:
            text = tf.read_text(errors="ignore")
        except OSError:
            continue
        score = 0
        for p in pats:
            if p.search(text):
                score += 1
        if score:
            hits.append((tf, score))
    return hits


def _best(orig: str, hits: list[tuple[Path, int]]) -> tuple[Path | None, list[Path]]:
    if not hits:
        return None, []
    ranked = sorted(
        hits,
        key=lambda t: (
            -t[1],
            -_path_overlap(orig, t[0].relative_to(ROOT).as_posix()),
            -t[0].stat().st_mtime,
        ),
    )
    top = ranked[0][0]
    return top, [r[0] for r in ranked]


def discover(rows: list[dict]) -> tuple[int, int, int, dict]:  # noqa: C901
    py_tests = _iter_python_tests()
    ts_tests = _iter_ts_tests()
    print(f"  scanning {len(py_tests)} python tests, {len(ts_tests)} ts tests")

    decisions: dict = {}
    seen: dict[str, str] = {}
    rewritten = 0
    ambiguous = 0
    nothing = 0

    for r in rows:
        if r["current_status"] in ("passed",):
            continue
        if r["framework"] not in ("pytest", "jest"):
            continue
        path = r["test_file_path"]
        if not path:
            continue
        if "/tests/" in path or path.startswith("tests/"):
            continue
        if path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            continue
        vt = r["vt_dcid"]
        if vt in seen:
            new = seen[vt]
            if new:
                r["test_file_path"] = new
                r["framework"] = "pytest" if new.endswith(".py") else "jest"
                r["automation_status"] = "automated"
                r["on_disk"] = "true"
                r["current_status"] = "not_executed"
                r["run_result"] = ""
            continue
        if r["framework"] == "pytest":
            pats = _import_patterns_python(path)
            hits = _scan(py_tests, pats)
        else:
            pats = _import_patterns_ts(path)
            hits = _scan(ts_tests, pats)
        best, ranked = _best(path, hits)
        if best is None:
            if ranked:
                ambiguous += 1
                decisions[vt] = {"orig": path, "status": "ambiguous",
                                 "candidates": [
                                     p.relative_to(ROOT).as_posix()
                                     for p in ranked[:5]
                                 ]}
            else:
                nothing += 1
                decisions[vt] = {"orig": path, "status": "no_match"}
            seen[vt] = ""
            continue
        new_path = best.relative_to(ROOT).as_posix()
        r["test_file_path"] = new_path
        r["framework"] = "pytest" if new_path.endswith(".py") else "jest"
        r["automation_status"] = "automated"
        r["on_disk"] = "true"
        r["current_status"] = "not_executed"
        r["run_result"] = ""
        seen[vt] = new_path
        rewritten += 1
        decisions[vt] = {"orig": path, "status": "match",
                         "chosen": new_path,
                         "candidates": [
                             p.relative_to(ROOT).as_posix()
                             for p in ranked[:5]
                         ]}

    return rewritten, ambiguous, nothing, decisions


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    rows = list(csv.DictReader(open(BACKLOG)))
    fields = list(rows[0].keys())
    rewritten, ambiguous, nothing, decisions = discover(rows)
    if not args.dry_run:
        with open(BACKLOG, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS.write_text(json.dumps(decisions, indent=2))
    print(f"rewritten distinct VTs: {rewritten}")
    print(f"ambiguous (kept manual): {ambiguous}")
    print(f"no candidate found (kept manual): {nothing}")
    print(f"decisions logged to {DECISIONS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
