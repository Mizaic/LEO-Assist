"""Cancer cases by year by end status.

Each EpisodeOfCare is bucketed by:
  - year: earliest milestone year (referral -> first_seen -> diagnosis ->
    end_date), so every episode lands in some year
  - status: ep.status (closed_benign / completed / in_progress /
    stale_post_specialist / stale_no_diagnosis / merged)

Reports two views:
  1. Episodes by (year, status) - everything
  2. Distinct patients by (year, status), excluding 'merged' duplicates
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

Q = """
MATCH (ep:EpisodeOfCare)
OPTIONAL MATCH (e_ref:Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep)
WITH ep, min(date(e_ref.date)) AS d_referral
OPTIONAL MATCH (e_fs:Encounter)-[:IS_PART_OF {milestone_type: 'first_seen'}]->(ep)
WITH ep, d_referral, min(date(e_fs.date)) AS d_first_seen
OPTIONAL MATCH (e_dx:Encounter)
              -[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
WITH ep, d_referral, d_first_seen, min(date(e_dx.date)) AS d_diagnosis
OPTIONAL MATCH (e_tx:Encounter)
              -[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
WITH ep, d_referral, d_first_seen, d_diagnosis,
     min(date(e_tx.date)) AS d_treatment
RETURN
    ep.episode_id   AS episode_id,
    ep.patient_id   AS patient_id,
    coalesce(ep.cancer_type, 'non_site_specific') AS cancer_type,
    coalesce(ep.status, '<null>')                 AS status,
    coalesce(ep.letter_inferred_benign, false)    AS letter_inferred_benign,
    coalesce(ep.referral_date, toString(d_referral))     AS ep_ref_date,
    coalesce(ep.first_seen_date, toString(d_first_seen)) AS ep_fs_date,
    toString(d_referral)   AS d_referral,
    toString(d_first_seen) AS d_first_seen,
    toString(d_diagnosis)  AS d_diagnosis,
    toString(d_treatment)  AS d_treatment,
    toString(date(ep.end_date)) AS d_end
"""


def _year(s) -> int | None:
    if not s or s in ("None", "null"):
        return None
    try:
        return int(str(s)[:4])
    except (TypeError, ValueError):
        return None


def _episode_year(r) -> int | None:
    """Pick the earliest meaningful year for the episode."""
    candidates = [
        _year(r.get("d_referral")),
        _year(r.get("ep_ref_date")),
        _year(r.get("d_first_seen")),
        _year(r.get("ep_fs_date")),
        _year(r.get("d_diagnosis")),
        _year(r.get("d_treatment")),
        _year(r.get("d_end")),
    ]
    candidates = [y for y in candidates if y is not None]
    return min(candidates) if candidates else None


# Logical end status: a patient-facing label combining status +
# diagnosis/benign/treatment milestones.
def _end_status(r) -> str:
    status = r.get("status") or "<null>"
    has_dx = bool(r.get("d_diagnosis"))
    has_tx = bool(r.get("d_treatment"))
    benign = (
        status == "closed_benign"
        or bool(r.get("letter_inferred_benign"))
    )
    if status == "merged":
        return "merged_duplicate"
    if benign:
        return "benign_outcome"
    if status == "completed" and has_dx and has_tx:
        return "diagnosed_and_treated"
    if status == "completed" and has_dx:
        return "diagnosed_no_treatment_yet"
    if status == "completed":
        return "completed_no_diagnosis"
    if status == "in_progress":
        return "in_progress"
    if status in ("stale_post_specialist", "stale_no_diagnosis"):
        return status
    return status


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = list(c.run(Q))
    finally:
        c.close()

    # ---- View 1: episodes by (year, raw status) ---------------------------
    by_status: dict[tuple[int | str, str], int] = defaultdict(int)
    statuses: set[str] = set()
    years: set[int | str] = set()
    for r in rows:
        y = _episode_year(r) or "unknown"
        status = r.get("status") or "<null>"
        by_status[(y, status)] += 1
        statuses.add(status)
        years.add(y)

    statuses_sorted = sorted(statuses)
    years_sorted = sorted(years, key=lambda x: (isinstance(x, str), x))

    print()
    print("View 1 - Episode counts by year by raw ep.status")
    print("=" * 92)
    header = f"{'Year':<8}" + "".join(f"{s[:18]:>20}" for s in statuses_sorted) + f"{'TOTAL':>8}"
    print(header)
    print("-" * len(header))
    col_totals = {s: 0 for s in statuses_sorted}
    for y in years_sorted:
        row = f"{str(y):<8}"
        rt = 0
        for s in statuses_sorted:
            n = by_status.get((y, s), 0)
            rt += n
            col_totals[s] += n
            row += f"{n:>20d}"
        row += f"{rt:>8d}"
        print(row)
    print("-" * len(header))
    total_row = f"{'TOTAL':<8}"
    for s in statuses_sorted:
        total_row += f"{col_totals[s]:>20d}"
    total_row += f"{sum(col_totals.values()):>8d}"
    print(total_row)

    # ---- View 2: distinct patients by (year, end_status), no merged -------
    pts_by_end: dict[tuple[int | str, str], set[str]] = defaultdict(set)
    end_statuses: set[str] = set()
    for r in rows:
        end = _end_status(r)
        if end == "merged_duplicate":
            continue
        pid = r.get("patient_id")
        if not pid:
            continue
        y = _episode_year(r) or "unknown"
        pts_by_end[(y, end)].add(pid)
        end_statuses.add(end)

    end_statuses_sorted = sorted(end_statuses)
    print()
    print("View 2 - Distinct patients by year by logical end status")
    print("(merged duplicates excluded; a patient counts once per status per year)")
    print("=" * 110)
    header = f"{'Year':<8}" + "".join(f"{s[:22]:>24}" for s in end_statuses_sorted) + f"{'TOTAL':>8}"
    print(header)
    print("-" * len(header))
    col_totals_p: dict[str, set[str]] = {s: set() for s in end_statuses_sorted}
    for y in years_sorted:
        if y == "unknown" and not any(
            (y, s) in pts_by_end for s in end_statuses_sorted
        ):
            continue
        row = f"{str(y):<8}"
        rt: set[str] = set()
        for s in end_statuses_sorted:
            pts = pts_by_end.get((y, s), set())
            row += f"{len(pts):>24d}"
            rt |= pts
            col_totals_p[s] |= pts
        row += f"{len(rt):>8d}"
        print(row)
    print("-" * len(header))
    total_row = f"{'TOTAL':<8}"
    grand: set[str] = set()
    for s in end_statuses_sorted:
        total_row += f"{len(col_totals_p[s]):>24d}"
        grand |= col_totals_p[s]
    total_row += f"{len(grand):>8d}"
    print(total_row)

    # ---- View 3: by-year confirmed-cancer split (the headline) ------------
    print()
    print("View 3 - Headline: cancer cases by year (distinct patients)")
    print("=" * 80)
    cohorts = {
        "referred":              ("d_referral", "ep_ref_date"),
        "diagnosed_or_treated":  ("__dx_or_tx__",),
        "diagnosed":             ("d_diagnosis",),
        "treated":               ("d_treatment",),
        "benign_outcome":        ("__benign_end__",),
    }
    pts_cohort_year: dict[tuple[str, int], set[str]] = defaultdict(set)
    cohort_years: set[int] = set()
    for r in rows:
        if (r.get("status") or "") == "merged":
            continue
        pid = r.get("patient_id")
        if not pid:
            continue
        ref_y = _year(r.get("d_referral")) or _year(r.get("ep_ref_date"))
        dx_y = _year(r.get("d_diagnosis"))
        tx_y = _year(r.get("d_treatment"))
        is_benign = (
            r.get("status") == "closed_benign"
            or bool(r.get("letter_inferred_benign"))
        )
        bn_y = _year(r.get("d_end")) if is_benign else None
        if ref_y is not None:
            pts_cohort_year[("referred", ref_y)].add(pid)
            cohort_years.add(ref_y)
        if dx_y is not None:
            pts_cohort_year[("diagnosed", dx_y)].add(pid)
            pts_cohort_year[("diagnosed_or_treated", dx_y)].add(pid)
            cohort_years.add(dx_y)
        if tx_y is not None:
            pts_cohort_year[("treated", tx_y)].add(pid)
            pts_cohort_year[("diagnosed_or_treated", tx_y)].add(pid)
            cohort_years.add(tx_y)
        if bn_y is not None:
            pts_cohort_year[("benign_outcome", bn_y)].add(pid)
            cohort_years.add(bn_y)

    cohort_order = ["referred", "diagnosed", "treated", "diagnosed_or_treated", "benign_outcome"]
    print(f"{'Year':<6}" + "".join(f"{c:>22}" for c in cohort_order))
    print("-" * 116)
    for y in sorted(cohort_years):
        row = f"{y:<6}"
        for c in cohort_order:
            row += f"{len(pts_cohort_year.get((c, y), set())):>22d}"
        print(row)


if __name__ == "__main__":
    main()
