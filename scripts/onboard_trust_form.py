"""Teach a form, run its golden letter, and print the go-live gate.

Usage:
    python scripts/onboard_trust_form.py \\
        --case-dir tests/fixtures/golden_corpus/rk5_117038_demo-v1

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.referral_quality.onboarding_gate import evaluate_onboarding  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Teach a form and run its golden letter as a go-live gate."
    )
    parser.add_argument(
        "--case-dir",
        required=True,
        help="Folder with case.json, letter.md and form_schema.json",
    )
    args = parser.parse_args(argv)
    report = evaluate_onboarding(Path(args.case_dir))
    _print_report(report)
    return 0 if report.ready else 1


def _print_report(report: object) -> None:
    ready = bool(getattr(report, "ready"))
    print("ready" if ready else "not ready")
    print(f"coverage_incomplete={getattr(report, 'coverage_incomplete')}")
    print(f"completeness_assessable={getattr(report, 'completeness_assessable')}")
    print(f"checks={', '.join(getattr(report, 'checks') or [])}")
    contamination = list(getattr(report, "contamination") or [])
    if contamination:
        print(f"contamination={len(contamination)}")
        for hit in contamination:
            print(f"  {hit.region}: {hit.fact_text}")
    for error in getattr(report, "errors") or []:
        print(f"error: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
