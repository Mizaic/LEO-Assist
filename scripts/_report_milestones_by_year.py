"""Per-year cohort report: distinct patients reaching each pathway milestone.

For each episode the milestone date is taken from the encounter that carries
the IS_PART_OF {milestone_type: ...} edge (earliest per milestone). Benign
outcome is taken from EpisodeOfCare.end_date when status='closed_benign' or
letter_inferred_benign=true.

A patient is counted in a year for a milestone if any of their episodes
reached that milestone in that calendar year.
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

Q_MILESTONE_DATES = """
MATCH (ep:EpisodeOfCare)
OPTIONAL MATCH (e_ref:Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep)
WITH ep, min(date(e_ref.date)) AS d_referral
OPTIONAL MATCH (e_fs:Encounter)-[:IS_PART_OF {milestone_type: 'first_seen'}]->(ep)
WITH ep, d_referral, min(date(e_fs.date)) AS d_first_seen
OPTIONAL MATCH (e_dx:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
WITH ep, d_referral, d_first_seen, min(date(e_dx.date)) AS d_diagnosis
OPTIONAL MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
WITH ep, d_referral, d_first_seen, d_diagnosis,
     min(date(e_tx.date)) AS d_treatment
RETURN
    ep.patient_id   AS patient_id,
    ep.episode_id   AS episode_id,
    ep.status       AS status,
    coalesce(ep.letter_inferred_benign, false) AS letter_inferred_benign,
    coalesce(ep.referral_date, toString(d_referral))   AS ep_referral_date,
    coalesce(ep.first_seen_date, toString(d_first_seen)) AS ep_first_seen_date,
    toString(d_referral)  AS d_referral,
    toString(d_first_seen) AS d_first_seen,
    toString(d_diagnosis)  AS d_diagnosis,
    toString(d_treatment)  AS d_treatment,
    toString(date(ep.end_date)) AS d_end
"""


def _year(s: str | None) -> int | None:
    if not s or s in ("None", "null"):
        return None
    try:
        return int(s[:4])
    except (TypeError, ValueError):
        return None


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(Q_MILESTONE_DATES)
    finally:
        c.close()

    by_year: dict[int, dict[str, set[str]]] = defaultdict(
        lambda: {
            "referral": set(),
            "first_seen": set(),
            "diagnosis_or_benign": set(),
            "diagnosis": set(),
            "benign": set(),
            "first_treatment": set(),
        }
    )

    for r in rows:
        pid = r["patient_id"]
        if not pid:
            continue
        # Per-milestone year (use the encounter-derived date when present,
        # otherwise fall back to the EpisodeOfCare property)
        ref_y = _year(r.get("d_referral")) or _year(r.get("ep_referral_date"))
        fs_y = _year(r.get("d_first_seen")) or _year(r.get("ep_first_seen_date"))
        dx_y = _year(r.get("d_diagnosis"))
        tx_y = _year(r.get("d_treatment"))

        status = r.get("status")
        is_benign = (
            status == "closed_benign" or bool(r.get("letter_inferred_benign"))
        )
        benign_y = _year(r.get("d_end")) if is_benign else None

        if ref_y:
            by_year[ref_y]["referral"].add(pid)
        if fs_y:
            by_year[fs_y]["first_seen"].add(pid)
        if dx_y:
            by_year[dx_y]["diagnosis"].add(pid)
            by_year[dx_y]["diagnosis_or_benign"].add(pid)
        if benign_y:
            by_year[benign_y]["benign"].add(pid)
            by_year[benign_y]["diagnosis_or_benign"].add(pid)
        if tx_y:
            by_year[tx_y]["first_treatment"].add(pid)

    print()
    print(
        "{:<6} | {:>9} | {:>11} | {:>9} | {:>9} | {:>20} | {:>16}".format(
            "Year",
            "Referral",
            "First seen",
            "Diagnosis",
            "Benign",
            "Diagnosis or benign",
            "First treatment",
        )
    )
    print("-" * 102)
    for year in sorted(by_year.keys()):
        m = by_year[year]
        print(
            "{:<6} | {:>9d} | {:>11d} | {:>9d} | {:>9d} | {:>20d} | {:>16d}".format(
                year,
                len(m["referral"]),
                len(m["first_seen"]),
                len(m["diagnosis"]),
                len(m["benign"]),
                len(m["diagnosis_or_benign"]),
                len(m["first_treatment"]),
            )
        )

    totals = {
        k: len(set().union(*[by_year[y][k] for y in by_year]))
        for k in (
            "referral",
            "first_seen",
            "diagnosis",
            "benign",
            "diagnosis_or_benign",
            "first_treatment",
        )
    }
    print("-" * 102)
    print(
        "{:<6} | {:>9d} | {:>11d} | {:>9d} | {:>9d} | {:>20d} | {:>16d}".format(
            "ALL",
            totals["referral"],
            totals["first_seen"],
            totals["diagnosis"],
            totals["benign"],
            totals["diagnosis_or_benign"],
            totals["first_treatment"],
        )
    )
    print("\n(Each cell = distinct patients with at least one episode reaching")
    print(" that milestone in that calendar year. ALL row de-dups across years.)")


if __name__ == "__main__":
    main()
