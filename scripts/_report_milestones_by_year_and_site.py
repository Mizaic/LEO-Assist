"""Per-year, per-cancer-site milestone cohort report.

For each EpisodeOfCare we read:
  - cancer_type
  - referral / first_seen / diagnosis_confirmed / treatment_started dates
    (taken from the IS_PART_OF{milestone_type:...} edges)
  - benign closure date (from end_date when status='closed_benign' or
    letter_inferred_benign=true)

A patient is counted in a (year, site) cell for a milestone if any of
their episodes for that site reached that milestone in that calendar
year. Merged duplicate episodes are excluded.
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
WHERE coalesce(ep.status, '') <> 'merged'
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
    ep.patient_id  AS patient_id,
    coalesce(ep.cancer_type, 'non_site_specific') AS cancer_type,
    ep.status      AS status,
    coalesce(ep.letter_inferred_benign, false) AS letter_inferred_benign,
    coalesce(ep.referral_date,   toString(d_referral))   AS ep_ref_date,
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


MILESTONES = ["referral", "first_seen", "diagnosis", "benign", "treatment"]


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = list(c.run(Q))
    finally:
        c.close()

    cells: dict[tuple[int, str], dict[str, set[str]]] = defaultdict(
        lambda: {m: set() for m in MILESTONES}
    )

    for r in rows:
        pid = r["patient_id"]
        site = r["cancer_type"] or "non_site_specific"
        if not pid:
            continue
        is_benign = (
            r.get("status") == "closed_benign"
            or bool(r.get("letter_inferred_benign"))
        )
        events = {
            "referral":  _year(r.get("d_referral"))  or _year(r.get("ep_ref_date")),
            "first_seen": _year(r.get("d_first_seen")) or _year(r.get("ep_fs_date")),
            "diagnosis": _year(r.get("d_diagnosis")),
            "benign":    _year(r.get("d_end")) if is_benign else None,
            "treatment": _year(r.get("d_treatment")),
        }
        for milestone, y in events.items():
            if y is not None:
                cells[(y, site)][milestone].add(pid)

    # ---- table ------------------------------------------------------------
    years = sorted({y for y, _ in cells.keys()})
    sites = sorted({s for _, s in cells.keys()})
    if "non_site_specific" in sites:
        sites = [s for s in sites if s != "non_site_specific"] + ["non_site_specific"]

    print()
    print("Per-year, per-cancer-site milestone cohort")
    print("=" * 92)
    header = (
        f"{'Year':<6}{'Site':<22}"
        f"{'Ref':>6}{'1st seen':>10}{'Diag':>6}"
        f"{'Benign':>8}{'Tx':>5}{'Ref->Tx':>9}"
    )
    print(header)
    print("-" * len(header))
    for y in years:
        for s in sites:
            cell = cells.get((y, s))
            if not cell:
                continue
            ref = len(cell["referral"])
            fs = len(cell["first_seen"])
            dx = len(cell["diagnosis"])
            bn = len(cell["benign"])
            tx = len(cell["treatment"])
            ref_to_tx = len(cell["referral"] & cell["treatment"])
            print(
                f"{y:<6}{s:<22}"
                f"{ref:>6}{fs:>10}{dx:>6}{bn:>8}{tx:>5}{ref_to_tx:>9}"
            )
        print("-" * len(header))

    # ---- summary by cancer site (across all years) ------------------------
    site_totals: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {m: set() for m in MILESTONES}
    )
    for (y, s), cell in cells.items():
        for m in MILESTONES:
            site_totals[s][m] |= cell[m]

    print()
    print("Cancer-site totals (distinct patients across all years)")
    print("=" * 80)
    print(
        f"{'Site':<22}{'Ref':>6}{'1st seen':>10}{'Diag':>6}"
        f"{'Benign':>8}{'Tx':>5}{'Ref->Tx':>9}{'Diag->Tx':>10}"
    )
    print("-" * 80)
    grand: dict[str, set[str]] = {m: set() for m in MILESTONES}
    for s in sites:
        cell = site_totals[s]
        ref = len(cell["referral"])
        fs = len(cell["first_seen"])
        dx = len(cell["diagnosis"])
        bn = len(cell["benign"])
        tx = len(cell["treatment"])
        ref_tx = len(cell["referral"] & cell["treatment"])
        dx_tx = len(cell["diagnosis"] & cell["treatment"])
        print(
            f"{s:<22}{ref:>6}{fs:>10}{dx:>6}{bn:>8}{tx:>5}{ref_tx:>9}{dx_tx:>10}"
        )
        for m in MILESTONES:
            grand[m] |= cell[m]
    print("-" * 80)
    print(
        f"{'TOTAL (distinct)':<22}"
        f"{len(grand['referral']):>6}{len(grand['first_seen']):>10}"
        f"{len(grand['diagnosis']):>6}{len(grand['benign']):>8}"
        f"{len(grand['treatment']):>5}"
    )


if __name__ == "__main__":
    main()
