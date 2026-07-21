"""CI guard -- warn (non-blocking) when a new FastAPI router grows too large.

2026-07 CTO peer-review item 2 (core-api router decomposition), step 5:
"Add a one-time size guard ... to warn on new routers >400 LOC or >15
handlers. Not blocking on first pass."

This checks only NEW router files introduced by a change (added, not
modified) -- existing large routers (patients.py, pipeline.py, and the
training.py sub-router split itself, several of which exceed the ~800 LOC
soft target from the god-service decomposition) are accepted debt with
their own tracked follow-ups, not something this guard should re-flag on
every unrelated PR that happens to touch them.

Run modes:
  --report              print LOC/handler counts for every router; never fail
  --changed-since REF   only check router files added since git ref REF
                         (falls back to warn-only "no base ref" message)

This is intentionally advisory: it always exits 0. It writes `::warning::`
lines so GitHub Actions surfaces them in the PR checks UI without failing
the build, per the plan's "not blocking on first pass" instruction.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MAX_LOC = 400
MAX_HANDLERS = 15

ROUTER_DIR_GLOBS = [
    "services/api/app/routers/*.py",
    "services/terminology_api/app/routers/*.py",
    "services/fhir_api/app/routers/*.py",
    "services/analytics_api/app/routers/*.py",
]

EXCLUDE_NAMES = {"__init__.py"}


def _count_loc(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(1 for ln in lines if ln.strip())


def _count_handlers(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return sum(
        1
        for line in text.splitlines()
        if line.lstrip().startswith("@router.")
        and any(
            line.lstrip().startswith(f"@router.{method}(")
            for method in ("get", "post", "put", "patch", "delete", "websocket")
        )
    )


def _router_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ROUTER_DIR_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted(p for p in files if p.name not in EXCLUDE_NAMES)


def _added_files_since(ref: str) -> set[Path] | None:
    """Return the set of router files added (not modified) since `ref`.

    Returns None if the diff could not be computed (e.g. no such ref, or
    shallow clone without history) so the caller can skip silently.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=A", ref, "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    added = set()
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[1].endswith(".py"):
            added.add((ROOT / parts[1]).resolve())
    return added


def _report_row(path: Path) -> tuple[str, int, int]:
    rel = path.relative_to(ROOT).as_posix()
    return rel, _count_loc(path), _count_handlers(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print LOC/handler counts for every router (no filtering).",
    )
    parser.add_argument(
        "--changed-since",
        metavar="REF",
        help="Only warn on router files added since this git ref.",
    )
    args = parser.parse_args()

    routers = _router_files()
    if args.report:
        print(f"{'router':<70} {'loc':>6} {'handlers':>9}")
        for path in routers:
            rel, loc, handlers = _report_row(path)
            print(f"{rel:<70} {loc:>6} {handlers:>9}")
        return 0

    if args.changed_since:
        added = _added_files_since(args.changed_since)
        if added is None:
            print(
                f"router_size_guard: could not diff against {args.changed_since!r}; "
                "skipping (non-blocking)."
            )
            return 0
        candidates = [p for p in routers if p.resolve() in added]
    else:
        candidates = routers

    warned = False
    for path in candidates:
        rel, loc, handlers = _report_row(path)
        over_loc = loc > MAX_LOC
        over_handlers = handlers > MAX_HANDLERS
        if not (over_loc or over_handlers):
            continue
        warned = True
        reasons = []
        if over_loc:
            reasons.append(f"{loc} LOC (soft limit {MAX_LOC})")
        if over_handlers:
            reasons.append(f"{handlers} handlers (soft limit {MAX_HANDLERS})")
        print(
            f"::warning file={rel}::New router {rel} is large: "
            f"{'; '.join(reasons)}. Consider splitting by feature area "
            "(see services/api/app/routers/training.py's sub-router split "
            "for the pattern) before it grows into god-service territory."
        )

    if not warned:
        print("router_size_guard: no new router exceeds the soft limits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
