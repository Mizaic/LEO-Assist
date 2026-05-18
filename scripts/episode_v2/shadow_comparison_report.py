"""Build the v1-vs-v2 shadow comparison report.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

Reads :EpisodeShadowRun nodes accumulated during the one-week
shadow window and the labelled regression cohort
(compliance/episode-v2-regression-cohort.json) and emits a
markdown + json report covering:

  - per-patient agreement (Jaccard over episode ids)
  - cohort-wide auto-case agreement rate
  - regression-cohort recall (did v2 produce ANY episodes for each
    labelled patient?)
  - top-N divergent patients with their added/dropped lists

Usage::

    python -m scripts.episode_v2.shadow_comparison_report \
        --cohort compliance/episode-v2-regression-cohort.json \
        --out compliance/episode-v2-shadow-report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from libs.episode_learning.shadow_run import (
    CohortShadowReport,
    ShadowComparison,
    aggregate_cohort_report,
)

logger = logging.getLogger(__name__)


class GraphRunner(Protocol):
    def run(self, cypher: str, **params: Any) -> Any: ...


READ_SHADOW_RUNS = """
MATCH (s:EpisodeShadowRun)
WHERE s.run_at >= datetime($since)
RETURN s.patient_id     AS patient_id,
       s.run_at         AS run_at,
       s.v1_episode_ids AS v1_episode_ids,
       s.v2_episode_ids AS v2_episode_ids,
       s.agreement      AS agreement,
       s.added_in_v2    AS added_in_v2,
       s.dropped_in_v2  AS dropped_in_v2
ORDER BY s.run_at DESC
"""


def _row_to_comparison(row: dict[str, Any]) -> ShadowComparison:
    run_at = row.get("run_at")
    if hasattr(run_at, "to_native"):
        run_at = run_at.to_native()
    if not isinstance(run_at, datetime):
        run_at = datetime.now(timezone.utc)
    return ShadowComparison(
        patient_id=str(row.get("patient_id") or ""),
        run_at=run_at,
        v1_episode_ids=tuple(row.get("v1_episode_ids") or []),
        v2_episode_ids=tuple(row.get("v2_episode_ids") or []),
        agreement=float(row.get("agreement") or 0.0),
        added_in_v2=tuple(row.get("added_in_v2") or []),
        dropped_in_v2=tuple(row.get("dropped_in_v2") or []),
    )


def load_comparisons(
    runner: GraphRunner,
    *,
    since: datetime,
) -> list[ShadowComparison]:
    """Read all shadow-run rows since the given cutoff."""
    rows = runner.run(READ_SHADOW_RUNS, since=since.isoformat()) or []
    return [_row_to_comparison(r) for r in rows]


def load_cohort_patient_ids(cohort_path: Path) -> list[str]:
    """Load the regression-cohort patient ids."""
    if not cohort_path.exists():
        return []
    payload = json.loads(cohort_path.read_text(encoding="utf-8"))
    cohort = payload.get("cohort") or []
    return [str(c.get("patient_id")) for c in cohort if c.get("patient_id")]


def report_to_markdown(report: CohortShadowReport) -> str:
    """Render the cohort report as a human-readable markdown block."""
    lines: list[str] = []
    lines.append("# Episode Detector v2 -- Shadow Comparison Report")
    lines.append("")
    lines.append(f"- Patients evaluated: {report.patients_evaluated}")
    lines.append(
        f"- Auto-case agreement rate: {report.auto_case_agreement_rate:.2%}"
    )
    lines.append(f"- Regression-cohort recall: {report.regression_recall:.2%}")
    lines.append(f"- Fully agreeing: {len(report.fully_agreeing_patients)}")
    lines.append(f"- Diverging: {len(report.diverging_patients)}")
    lines.append("")
    if report.diverging_patients:
        lines.append("## Top divergent patients")
        lines.append("")
        lines.append("| Patient | Agreement | v1 | v2 | added in v2 | dropped in v2 |")
        lines.append("|---|---|---|---|---|---|")
        for row in report.rows:
            if row["agreement"] >= 1.0:
                continue
            lines.append(
                "| {pid} | {agree:.2%} | {v1} | {v2} | {added} | {dropped} |".format(
                    pid=row["patient_id"],
                    agree=row["agreement"],
                    v1=row["v1_count"],
                    v2=row["v2_count"],
                    added=", ".join(row["added_in_v2"]) or "-",
                    dropped=", ".join(row["dropped_in_v2"]) or "-",
                )
            )
    return "\n".join(lines) + "\n"


def report_to_json(report: CohortShadowReport) -> dict[str, Any]:
    return {
        "patients_evaluated": report.patients_evaluated,
        "auto_case_agreement_rate": report.auto_case_agreement_rate,
        "regression_recall": report.regression_recall,
        "fully_agreeing_patients": list(report.fully_agreeing_patients),
        "diverging_patients": list(report.diverging_patients),
        "rows": list(report.rows),
    }


def build_report(
    runner: GraphRunner,
    *,
    cohort_path: Path,
    since: datetime,
) -> CohortShadowReport:
    """Top-level entry point. Loads + aggregates."""
    comparisons = load_comparisons(runner, since=since)
    cohort_ids = load_cohort_patient_ids(cohort_path)
    return aggregate_cohort_report(
        comparisons,
        regression_cohort_patient_ids=cohort_ids,
    )


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cohort",
        type=Path,
        default=Path("compliance/episode-v2-regression-cohort.json"),
        help="Path to the labelled regression cohort json.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("compliance/episode-v2-shadow-report.json"),
    )
    parser.add_argument(
        "--out-markdown",
        type=Path,
        default=Path("compliance/episode-v2-shadow-report.md"),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window of shadow runs to include (default 7 days).",
    )
    args = parser.parse_args(argv)

    from libs.graph_client import patient_graph_client

    since = datetime.now(timezone.utc).replace(microsecond=0)
    since = since.fromtimestamp(since.timestamp() - args.days * 86400, tz=timezone.utc)

    runner = patient_graph_client.PatientGraphClient()
    try:
        report = build_report(runner, cohort_path=args.cohort, since=since)
    finally:
        if hasattr(runner, "close"):
            runner.close()

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(report_to_json(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    args.out_markdown.write_text(report_to_markdown(report), encoding="utf-8")
    sys.stdout.write(
        f"Wrote shadow report to {args.out_json} and {args.out_markdown}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
