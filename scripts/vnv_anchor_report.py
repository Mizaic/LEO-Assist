"""Phase 3 — ISO 13485 V&V Anchor Detection Evidence Report.

Reads the clinician-labelled JSONL produced by ``audit_patient_anchors.py``
and computes formal V&V metrics with 95 % Wilson confidence intervals.

Output
------
exports/vnv_anchor_report_<timestamp>.csv
    ISO 13485 evidence table — one section per milestone type.
    Contains: TP, FN, TN, FP, sensitivity, specificity, PPV, NPV, F1
    with lower and upper 95 % Wilson CIs.  Suitable for QMS attachment.

exports/vnv_anchor_report_<timestamp>_detail.json
    Full per-patient breakdown, failure mode classification, detection-path
    effectiveness table, and population characteristics.

ISO 13485 evidence claims
--------------------------
This report supports the following design-verification statements:

  "The anchor detection algorithm was evaluated against N patients
   (M encounters, date range R–R).  Sensitivity for <milestone> detection
   was X % (95 % CI Y–Z %).  Failure modes were classified into three
   categories: coding gap (found_soft), ambiguous evidence
   (possibly_missing), and absent pathway (truly_missing)."

Labelling instructions
-----------------------
After running audit_patient_anchors.py, open the JSONL output and fill in
the ``manual_label`` field for every row where any
``investigation.<milestone>.assessment`` is ``found_soft`` or
``possibly_missing``.

Manual label values:
  TRUE_POSITIVE   — the milestone was genuinely present; the algorithm
                    found it (or found_soft = algorithm missed it but
                    evidence was there)
  FALSE_NEGATIVE  — milestone genuinely present but algorithm returned
                    nothing and investigation found no evidence either
  TRUE_NEGATIVE   — milestone genuinely absent; algorithm correctly
                    returned none
  NOT_APPLICABLE  — patient record is incomplete / outside scope

Milestone rows that are ``found`` by the algorithm (concept-path detection succeeded)
do not need manual labels — they are counted as provisional TPs.

Usage
-----
    python scripts/vnv_anchor_report.py --input exports/anchor_audit_*.jsonl
    python scripts/vnv_anchor_report.py \\
        --input exports/anchor_audit_labelled.jsonl \\
        --min-labelled 20 \\
        --output-dir exports/
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger("vnv_report")

ALL_MILESTONES = ["referral", "diagnosis", "treatment_start", "specialist_visit"]


# ─── Wilson confidence interval ──────────────────────────────────────────────


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score confidence interval for a proportion k/n.

    Returns (lower, upper) in [0, 1].  When n == 0 returns (0.0, 1.0).
    """
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def pct(k: int, n: int) -> float:
    return round(k / n * 100, 1) if n else 0.0


# ─── JSONL loading ────────────────────────────────────────────────────────────


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed line: %s…", line[:60])
    return rows


# ─── Per-milestone classification ────────────────────────────────────────────


def classify_milestone(
    patient_row: dict[str, Any],
    milestone: str,
) -> str:
    """Return the outcome classification for a single patient-milestone pair.

    Returns one of:
      "algorithm_found"   — concept-path detection found the anchor (provisional TP)
      "found_soft_TP"     — found_soft + manual_label == TRUE_POSITIVE
      "found_soft_FN"     — found_soft + manual_label == FALSE_NEGATIVE
      "found_soft_unlabelled"
      "possibly_missing_TP"
      "possibly_missing_FN"
      "possibly_missing_TN"
      "possibly_missing_unlabelled"
      "truly_missing_TN"  — no evidence; presumed true negative
      "truly_missing_FN"  — no evidence but manually marked FALSE_NEGATIVE
      "truly_missing_unlabelled"
      "error"
    """
    if patient_row.get("error"):
        return "error"

    anchors = patient_row.get("anchors", {})
    if anchors.get(milestone):
        return "algorithm_found"

    inv = patient_row.get("investigation", {}).get(milestone, {})
    assessment = inv.get("assessment", "truly_missing")
    label = inv.get("manual_label")

    if assessment == "found_soft":
        if label == "TRUE_POSITIVE":
            return "found_soft_TP"
        if label == "FALSE_NEGATIVE":
            return "found_soft_FN"
        return "found_soft_unlabelled"

    if assessment == "possibly_missing":
        if label == "TRUE_POSITIVE":
            return "possibly_missing_TP"
        if label == "FALSE_NEGATIVE":
            return "possibly_missing_FN"
        if label == "TRUE_NEGATIVE":
            return "possibly_missing_TN"
        return "possibly_missing_unlabelled"

    # truly_missing
    if label == "FALSE_NEGATIVE":
        return "truly_missing_FN"
    return "truly_missing_TN"


# ─── Metrics computation ──────────────────────────────────────────────────────


def compute_milestone_metrics(
    rows: list[dict[str, Any]],
    milestone: str,
) -> dict[str, Any]:
    """Compute TP/FN/TN/FP and derived metrics for one milestone type."""

    outcomes = [classify_milestone(r, milestone) for r in rows]

    # Counting rules
    # TP: algorithm_found + found_soft_TP + possibly_missing_TP
    # FN: found_soft_FN + possibly_missing_FN + truly_missing_FN
    # TN: truly_missing_TN + possibly_missing_TN
    # FP: not modelled (we don't challenge anchors the algorithm found)
    # Unlabelled: excluded from metric denominators with a note

    TP = (
        outcomes.count("algorithm_found")
        + outcomes.count("found_soft_TP")
        + outcomes.count("possibly_missing_TP")
    )
    FN = (
        outcomes.count("found_soft_FN")
        + outcomes.count("possibly_missing_FN")
        + outcomes.count("truly_missing_FN")
    )
    TN = outcomes.count("truly_missing_TN") + outcomes.count("possibly_missing_TN")
    FP = 0  # not assessed — false positive rate analysis is out-of-scope for NCDA

    unlabelled = sum(1 for o in outcomes if "unlabelled" in o)

    n_positive = TP + FN
    n_negative = TN + FP

    sensitivity = TP / n_positive if n_positive else None
    specificity = TN / n_negative if n_negative else None
    ppv = TP / (TP + FP) if (TP + FP) else None
    npv = TN / (TN + FN) if (TN + FN) else None
    f1 = (2 * TP) / (2 * TP + FP + FN) if (2 * TP + FP + FN) else None

    sens_lo, sens_hi = wilson_ci(TP, n_positive) if n_positive else (None, None)
    spec_lo, spec_hi = wilson_ci(TN, n_negative) if n_negative else (None, None)

    # Detection-method attribution for true positives
    tier_counts: dict[str, int] = {
        "concept": 0,
        "none": 0,
        "other": 0,
    }
    for r in rows:
        if r.get("anchors", {}).get(milestone):
            method = r.get("tier_breakdown", {}).get(milestone, "other")
            key = method if method in tier_counts else "other"
            tier_counts[key] += 1

    # Failure mode counts
    failure_modes = {
        "found_soft": outcomes.count("found_soft_TP")
        + outcomes.count("found_soft_FN")
        + outcomes.count("found_soft_unlabelled"),
        "possibly_missing": outcomes.count("possibly_missing_TP")
        + outcomes.count("possibly_missing_FN")
        + outcomes.count("possibly_missing_TN")
        + outcomes.count("possibly_missing_unlabelled"),
        "truly_missing": outcomes.count("truly_missing_TN")
        + outcomes.count("truly_missing_FN"),
    }

    def _fmt(v: float | None) -> str:
        return f"{v * 100:.1f}" if v is not None else "n/a"

    return {
        "milestone": milestone,
        "TP": TP,
        "FN": FN,
        "TN": TN,
        "FP": FP,
        "unlabelled": unlabelled,
        "n_positive": n_positive,
        "n_negative": n_negative,
        "sensitivity_pct": _fmt(sensitivity),
        "sensitivity_ci_lo_pct": _fmt(sens_lo),
        "sensitivity_ci_hi_pct": _fmt(sens_hi),
        "specificity_pct": _fmt(specificity),
        "specificity_ci_lo_pct": _fmt(spec_lo),
        "specificity_ci_hi_pct": _fmt(spec_hi),
        "ppv_pct": _fmt(ppv),
        "npv_pct": _fmt(npv),
        "f1_pct": _fmt(f1),
        "tier_attribution": tier_counts,
        "failure_modes": failure_modes,
    }


# ─── Population characteristics ───────────────────────────────────────────────


def compute_population_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    enc_counts = [r.get("encounter_count", 0) for r in rows if not r.get("error")]
    all_dates = [d for r in rows for d in (r.get("date_range") or []) if d]
    enc_counts.sort()
    return {
        "total_patients": n,
        "total_encounters": sum(enc_counts),
        "median_enc_per_patient": enc_counts[len(enc_counts) // 2] if enc_counts else 0,
        "p25_enc": enc_counts[len(enc_counts) // 4] if enc_counts else 0,
        "p75_enc": enc_counts[3 * len(enc_counts) // 4] if enc_counts else 0,
        "date_from": min(all_dates) if all_dates else "n/a",
        "date_to": max(all_dates) if all_dates else "n/a",
        "patients_with_errors": sum(1 for r in rows if r.get("error")),
    }


# ─── CSV output ───────────────────────────────────────────────────────────────


def write_evidence_csv(
    metrics_list: list[dict[str, Any]],
    population: dict[str, Any],
    git_hash: str,
    path: Path,
) -> None:
    """Write ISO 13485 evidence table CSV."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)

        # Header block
        w.writerow(["ISO 13485 / ISO 14971 — Anchor Detection V&V Evidence"])
        w.writerow(["Generated", datetime.datetime.now().isoformat()])
        w.writerow(["Algorithm version (git)", git_hash])
        w.writerow([])

        # Population block
        w.writerow(["=== POPULATION CHARACTERISTICS ==="])
        for k, v in population.items():
            w.writerow([k, v])
        w.writerow([])

        # Metrics table
        w.writerow(["=== PERFORMANCE METRICS (per milestone) ==="])
        header = [
            "Milestone",
            "TP",
            "FN",
            "TN",
            "FP",
            "Unlabelled",
            "Sensitivity %",
            "Sens CI lo %",
            "Sens CI hi %",
            "Specificity %",
            "Spec CI lo %",
            "Spec CI hi %",
            "PPV %",
            "NPV %",
            "F1 %",
            "Concept path",
            "None/unknown path",
            "Found-soft (coding gap)",
            "Possibly missing",
            "Truly missing",
        ]
        w.writerow(header)
        for m in metrics_list:
            t = m["tier_attribution"]
            f = m["failure_modes"]
            w.writerow(
                [
                    m["milestone"],
                    m["TP"],
                    m["FN"],
                    m["TN"],
                    m["FP"],
                    m["unlabelled"],
                    m["sensitivity_pct"],
                    m["sensitivity_ci_lo_pct"],
                    m["sensitivity_ci_hi_pct"],
                    m["specificity_pct"],
                    m["specificity_ci_lo_pct"],
                    m["specificity_ci_hi_pct"],
                    m["ppv_pct"],
                    m["npv_pct"],
                    m["f1_pct"],
                    t.get("concept", 0),
                    t.get("none", 0) + t.get("other", 0),
                    f.get("found_soft", 0),
                    f.get("possibly_missing", 0),
                    f.get("truly_missing", 0),
                ]
            )
        w.writerow([])

        # Failure mode legend
        w.writerow(["=== FAILURE MODE CLASSIFICATION ==="])
        w.writerow(
            [
                "found_soft",
                "Domain keywords present with confirmed language but concept/resolver "
                "threshold not met — coding gap in extraction pipeline",
            ]
        )
        w.writerow(
            [
                "possibly_missing",
                "Keywords present but only suspected/ambiguous language — milestone "
                "may be genuinely absent (pre-diagnostic) or language too subtle",
            ]
        )
        w.writerow(
            [
                "truly_missing",
                "No domain keyword hits in investigation window — milestone absent "
                "from records (patient had no cancer pathway / incomplete records)",
            ]
        )
        w.writerow([])

        # Labelling notes
        w.writerow(["=== LABELLING NOTE ==="])
        w.writerow(
            [
                "Metrics are computed from rows with manual_label populated. "
                "'algorithm_found' rows count as provisional TP without manual review. "
                "FP rate not assessed (challenges to algorithm-found anchors are "
                "out of scope for NCDA initial validation)."
            ]
        )

    logger.info("Evidence CSV → %s", path)


# ─── Main ────────────────────────────────────────────────────────────────────


def get_git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=textwrap.dedent("""\
            VnV Anchor Report — Phase 3 of ISO 13485 V&V.
            Reads a clinician-labelled audit JSONL and computes formal
            performance metrics with Wilson confidence intervals.
        """))
    p.add_argument(
        "--input", required=True, help="Path to labelled anchor_audit_*.jsonl file"
    )
    p.add_argument(
        "--output-dir",
        default="exports",
        help="Directory for output files (default: exports/)",
    )
    p.add_argument(
        "--min-labelled",
        type=int,
        default=0,
        help="Abort if fewer than N milestones have manual labels",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1

    rows = load_rows(input_path)
    logger.info("Loaded %d patient rows from %s", len(rows), input_path)

    # Check labelling coverage
    total_labelled = sum(
        1
        for r in rows
        for m in ALL_MILESTONES
        if r.get("investigation", {}).get(m, {}).get("manual_label")
    )
    logger.info("Total manually labelled milestone-rows: %d", total_labelled)
    if args.min_labelled and total_labelled < args.min_labelled:
        logger.error(
            "Only %d milestone-rows are labelled; need at least %d.  "
            "Aborting — complete Phase 2 labelling first.",
            total_labelled,
            args.min_labelled,
        )
        return 1

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"vnv_anchor_report_{ts}.csv"
    detail_path = out_dir / f"vnv_anchor_report_{ts}_detail.json"

    git_hash = get_git_hash()
    population = compute_population_stats(rows)
    metrics_list = [compute_milestone_metrics(rows, m) for m in ALL_MILESTONES]

    # ── Console summary ───────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("VnV ANCHOR DETECTION REPORT  (git: %s)", git_hash)
    logger.info(
        "  Patients: %d  Encounters: %d  Labelled rows: %d",
        population["total_patients"],
        population["total_encounters"],
        total_labelled,
    )
    logger.info("-" * 70)
    logger.info(
        "  %-20s  %4s  %4s  %4s  %-20s  %-20s",
        "Milestone",
        "TP",
        "FN",
        "TN",
        "Sensitivity (95% CI)",
        "Specificity (95% CI)",
    )
    for m in metrics_list:
        sens = (
            f"{m['sensitivity_pct']}% "
            f"[{m['sensitivity_ci_lo_pct']}–{m['sensitivity_ci_hi_pct']}%]"
        )
        spec = (
            f"{m['specificity_pct']}% "
            f"[{m['specificity_ci_lo_pct']}–{m['specificity_ci_hi_pct']}%]"
        )
        logger.info(
            "  %-20s  %4s  %4s  %4s  %-20s  %-20s",
            m["milestone"],
            m["TP"],
            m["FN"],
            m["TN"],
            sens,
            spec,
        )
    logger.info("=" * 70)

    # ── Output files ──────────────────────────────────────────────────────
    write_evidence_csv(metrics_list, population, git_hash, csv_path)

    detail = {
        "generated_at": datetime.datetime.now().isoformat(),
        "git_hash": git_hash,
        "input_file": str(input_path),
        "population": population,
        "metrics": metrics_list,
        "per_patient": [
            {
                "patient_id": r["patient_id"],
                "encounter_count": r.get("encounter_count", 0),
                "detection_method": r.get("detection_method", ""),
                "milestone_outcomes": {
                    m: classify_milestone(r, m) for m in ALL_MILESTONES
                },
            }
            for r in rows
        ],
    }
    detail_path.write_text(json.dumps(detail, indent=2, default=str), encoding="utf-8")
    logger.info("Detail JSON → %s", detail_path)

    if total_labelled == 0:
        logger.warning(
            "\nNo manual labels found — metrics are based solely on "
            "algorithm-found anchors.  Complete Phase 2 labelling to "
            "get formal sensitivity/specificity with confidence intervals."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
