"""Stage 12 - NCDA evaluation harness CLI.

Runs the metric helpers in
``services.analysis_worker.app.ncda_detector.evaluation`` against a JSON gold-vs-
prediction payload and prints a Markdown report.

Atlas trace
-----------
- DI: NCDA-DI-EVAL ("Eval harness must report per-role/per-cohort metrics, days
  error, breach-flag accuracy, and cohort-3 false alarms").
- DO: NCDA-DO-EVAL ("scripts/ncda/evaluate.py and tests/ncda/test_metrics_baseline.py").

Input file shape (JSON)::

    {
      "role_y_true": [...],            "role_y_pred": [...],
      "cohort_y_true": [...],          "cohort_y_pred": [...],
      "ftr_dx_days_pred": [...],       "ftr_dx_days_gold": [...],
      "breach_flags_pred": [...],      "breach_flags_gold": [...],
      "pair_recovered_ids": [...],     "pair_gold_ids": [...],
      "predicted_cohort_3_ids": [...], "gold_cohort_3_ids": [...]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.analysis_worker.app.ncda_detector.evaluation import evaluate


def _format_role_table(metrics: dict[str, dict[str, float]]) -> str:
    rows = ["| label | precision | recall | f1 | support |", "| --- | --- | --- | --- | --- |"]
    for label in sorted(metrics):
        m = metrics[label]
        rows.append(
            f"| {label} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |"
        )
    return "\n".join(rows)


def _format_report(metrics: dict) -> str:
    parts = ["# NCDA evaluation report\n"]
    parts.append("## Per-role metrics\n")
    parts.append(_format_role_table(metrics["role_metrics"]))
    parts.append("\n\n## Per-cohort metrics\n")
    parts.append(_format_role_table(metrics["cohort_metrics"]))
    parts.append("\n\n## Days error\n")
    parts.append(json.dumps(metrics["days_error"], indent=2))
    parts.append("\n\n## Breach flag accuracy\n")
    parts.append(json.dumps(metrics["breach_flag_accuracy"], indent=2))
    parts.append("\n\n## Coverage\n")
    parts.append(f"{metrics['coverage']}")
    parts.append("\n\n## Cohort-3 false alarm rate\n")
    parts.append(f"{metrics['cohort_3_false_alarm_rate']}")
    parts.append("\n")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NCDA detector evaluation harness.")
    parser.add_argument("--input", type=Path, required=True, help="Path to gold/pred JSON.")
    parser.add_argument("--output", type=Path, default=None, help="Optional report path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2

    payload = json.loads(args.input.read_text())
    metrics = evaluate(**payload)

    if args.json:
        report = json.dumps(metrics, indent=2)
    else:
        report = _format_report(metrics)

    if args.output:
        args.output.write_text(report)
    else:
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
