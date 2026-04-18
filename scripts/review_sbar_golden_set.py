#!/usr/bin/env python3
"""Interactive sign-off harness for the SBAR golden set.

After ``scripts/run_sbar_golden_set.py`` has produced a report
directory, this harness walks each fixture's report, prints the
clinical scenario, the rendered SBAR Markdown, the structural-check
verdict, and prompts the reviewer for an explicit pass/fail decision
plus a free-text comment. The signed ledger is written to
``signed_ledger.json`` inside the report directory and is the artefact
attached to the VT-LEO-AI-189 evidence bundle.

Usage:
    python3 scripts/review_sbar_golden_set.py
    python3 scripts/review_sbar_golden_set.py --reports-dir <path>
    python3 scripts/review_sbar_golden_set.py --reviewer "Dr A Clinician"
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_ROOT = _REPO_ROOT / "data" / "sbar-golden-set-reports"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_run_dir(root: Path) -> Path:
    if not root.exists():
        raise SystemExit(f"No reports directory at {root}; run the runner first.")
    candidates = sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"No run directories under {root}.")
    return candidates[0]


def _list_fixture_dirs(run_dir: Path) -> list[Path]:
    return sorted(
        p for p in run_dir.iterdir()
        if p.is_dir() and p.name.startswith("fixture-")
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def _ask(prompt: str) -> str:
    """input() wrapped so tests can monkeypatch."""
    return input(prompt)


def _hr() -> None:
    print("-" * 78)


# ---------------------------------------------------------------------------
# Per-fixture review
# ---------------------------------------------------------------------------


def _render_summary(structural: dict[str, Any]) -> str:
    overall = structural.get("overall", "?")
    failures = structural.get("failures") or []
    if not failures:
        return f"structural overall: {overall} (all checks passed)"
    head = f"structural overall: {overall} ({len(failures)} failure(s))"
    return head + "\n  - " + "\n  - ".join(failures)


def _render_fixture(fixture_dir: Path) -> dict[str, Any]:
    fixture = _read_yaml(fixture_dir / "fixture.yaml") or {}
    output = (fixture_dir / "output.md").read_text()
    structural = _read_json(fixture_dir / "structural_check.json")
    pathway = _read_json(fixture_dir / "pathway_hints.json")
    result = _read_json(fixture_dir / "result.json")

    print()
    _hr()
    print(f"Fixture {fixture.get('id', '?')} - {fixture.get('title', '')}")
    _hr()
    print("Clinical scenario:")
    print(fixture.get("clinical_scenario") or "  (no scenario provided)")
    print()
    print("Reviewer focus:")
    re = fixture.get("reviewer_expectations") or {}
    print(re.get("reviewer_focus") or "  (none recorded)")
    print()
    print("Rendered SBAR:")
    _hr()
    print(output)
    _hr()
    print(f"SBAR status: {result.get('status', '?')}")
    print(f"Errors:      {result.get('errors') or 'none'}")
    print(f"Pathway hints: {json.dumps(pathway, sort_keys=True)}")
    print(_render_summary(structural))
    _hr()

    return {
        "fixture_id": fixture.get("id"),
        "fixture_path": str(fixture_dir / "fixture.yaml"),
        "structural_overall": structural.get("overall"),
        "structural_failures": structural.get("failures") or [],
    }


def _prompt_verdict(default_skip: bool = False) -> tuple[str, str]:
    while True:
        choice = _ask(
            "Verdict [p]ass / [f]ail / [s]kip / [q]uit: "
        ).strip().lower()
        if choice in ("p", "pass"):
            verdict = "pass"
            break
        if choice in ("f", "fail"):
            verdict = "fail"
            break
        if choice in ("s", "skip"):
            verdict = "skip"
            break
        if choice in ("q", "quit"):
            verdict = "quit"
            break
        print("Please enter p, f, s or q.")
    if verdict in ("pass", "fail", "skip"):
        comment = _ask("Comment (optional, single line): ").strip()
    else:
        comment = ""
    return verdict, comment


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def _signed_ledger(
    run_dir: Path,
    reviewer: str,
    role: str,
    verdicts: list[dict[str, Any]],
) -> Path:
    ledger_path = run_dir / "signed_ledger.json"
    pass_count = sum(1 for v in verdicts if v.get("verdict") == "pass")
    fail_count = sum(1 for v in verdicts if v.get("verdict") == "fail")
    skip_count = sum(1 for v in verdicts if v.get("verdict") == "skip")

    all_pass = (
        fail_count == 0
        and skip_count == 0
        and pass_count == len(verdicts)
    )
    overall = "pass" if all_pass else "fail"

    ledger = {
        "vt_id": "VT-LEO-AI-189",
        "test_case_id": "VT-189-TC-009",
        "run_dir": str(run_dir),
        "signed_at": _now_iso(),
        "reviewer": reviewer,
        "reviewer_role": role,
        "overall": overall,
        "counts": {
            "pass": pass_count,
            "fail": fail_count,
            "skip": skip_count,
            "total": len(verdicts),
        },
        "verdicts": verdicts,
    }
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True))
    return ledger_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports-dir",
        default=None,
        help=(
            "Specific run directory to review "
            "(default: latest under data/sbar-golden-set-reports/)"
        ),
    )
    parser.add_argument(
        "--reviewer",
        default=None,
        help="Reviewer name; prompted if omitted.",
    )
    parser.add_argument(
        "--role",
        default=None,
        help=(
            "Reviewer role (e.g. 'Clinical Safety Officer'); "
            "prompted if omitted."
        ),
    )
    parser.add_argument(
        "--noninteractive",
        action="store_true",
        help="Skip prompting; record every fixture as 'skip' (CI smoke).",
    )
    args = parser.parse_args(argv)

    if args.reports_dir:
        run_dir = Path(args.reports_dir).resolve()
    else:
        run_dir = _latest_run_dir(DEFAULT_REPORTS_ROOT)
    print(f"Reviewing run: {run_dir}")

    fixture_dirs = _list_fixture_dirs(run_dir)
    if not fixture_dirs:
        raise SystemExit(f"No fixture-*/ subdirectories under {run_dir}.")

    if args.reviewer:
        reviewer = args.reviewer
    elif args.noninteractive:
        reviewer = "noninteractive"
    else:
        reviewer = _ask("Reviewer name: ").strip()
    if args.role:
        role = args.role
    elif args.noninteractive:
        role = "noninteractive"
    else:
        role = _ask("Reviewer role: ").strip()

    verdicts: list[dict[str, Any]] = []
    for fdir in fixture_dirs:
        summary = _render_fixture(fdir)
        if args.noninteractive:
            verdict, comment = "skip", "noninteractive run"
        else:
            verdict, comment = _prompt_verdict()
        if verdict == "quit":
            print("Quitting; partial ledger NOT written.")
            return 2
        verdicts.append(
            {
                **summary,
                "verdict": verdict,
                "comment": comment,
                "decided_at": _now_iso(),
            }
        )

    ledger_path = _signed_ledger(run_dir, reviewer, role, verdicts)
    print()
    print(f"Signed ledger: {ledger_path}")
    failed = sum(1 for v in verdicts if v.get("verdict") != "pass")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
