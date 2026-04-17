"""Pathway funnel investigation -- explain every gap.

Data extracted on 2025-12-30. Cutoffs used for 'still legitimate / in window':
  Referral waiting on first-seen        : after 2025-09-30 (90d window)
  First-seen waiting on diagnosis       : after 2025-09-30 (90d window)
  Diagnosis waiting on treatment        : after 2025-09-30 (90d window)

For every gap we surface a count and a sample so the user can verify rather
than trust a single aggregate number.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

EXTRACT_DATE = "2025-12-30"
WINDOW_CUTOFF = "2025-09-30"

# Per-episode milestone date view; reused across queries.
EP_VIEW = """
MATCH (ep:EpisodeOfCare)
OPTIONAL MATCH (e_ref:Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep)
WITH ep, min(date(e_ref.date)) AS d_referral
OPTIONAL MATCH (e_fs:Encounter)-[:IS_PART_OF {milestone_type: 'first_seen'}]->(ep)
WITH ep, d_referral, min(date(e_fs.date)) AS d_first_seen
OPTIONAL MATCH (e_dx:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
WITH ep, d_referral, d_first_seen, min(date(e_dx.date)) AS d_diagnosis
OPTIONAL MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
WITH ep, d_referral, d_first_seen, d_diagnosis, min(date(e_tx.date)) AS d_treatment
"""


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def run(c, q: str, **params):
    rows = c.run(q, **params)
    return [dict(r) for r in rows]


def show(rows, limit: int = 8) -> None:
    if not rows:
        print("  (no rows)")
        return
    for r in rows[:limit]:
        print("  ", r)
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more")


def q1_no_referral(c) -> None:
    header("Q1. First-seen or diagnosis WITHOUT a referral on the same episode")
    print("Hypothesis: A&E presentation, specialist-to-specialist, screening, or other route.")
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_referral, d_first_seen, d_diagnosis
        WHERE d_referral IS NULL AND (d_first_seen IS NOT NULL OR d_diagnosis IS NOT NULL)
        RETURN
            coalesce(ep.referral_route, '<null>') AS route,
            coalesce(ep.place_of_presentation, '<null>') AS place,
            count(DISTINCT ep) AS episodes,
            count(DISTINCT ep.patient_id) AS patients
        ORDER BY episodes DESC
        """,
    )
    print("By referral_route + place_of_presentation:")
    show(rows, 20)
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_referral, d_first_seen, d_diagnosis
        WHERE d_referral IS NULL AND (d_first_seen IS NOT NULL OR d_diagnosis IS NOT NULL)
        RETURN
            ep.patient_id AS pid,
            ep.cancer_type AS cancer,
            toString(d_first_seen) AS d_fs,
            toString(d_diagnosis) AS d_dx,
            coalesce(ep.referral_route, '<null>') AS route,
            coalesce(ep.place_of_presentation, '<null>') AS place,
            ep.status AS status
        ORDER BY pid
        LIMIT 12
        """,
    )
    print("Sample episodes:")
    show(rows, 12)


def q2_referral_no_first_seen(c) -> None:
    header("Q2. Referrals WITHOUT a first-seen milestone")
    print("Buckets: in-window (referral after 2025-09-30), DNA/cancelled, or missed.")
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_referral, d_first_seen
        WHERE d_referral IS NOT NULL AND d_first_seen IS NULL
        WITH ep, d_referral,
             CASE
               WHEN d_referral > date($cutoff) THEN 'in_window_under_90d'
               WHEN ep.status = 'closed_benign' THEN 'closed_benign_no_clinic_visit'
               WHEN ep.status = 'completed' THEN 'completed_no_first_seen'
               WHEN ep.status STARTS WITH 'stale' THEN 'auto_closed_stale'
               WHEN ep.auto_closed = true THEN 'auto_closed'
               ELSE coalesce(ep.status, 'in_progress')
             END AS bucket
        RETURN bucket, count(DISTINCT ep) AS episodes, count(DISTINCT ep.patient_id) AS patients
        ORDER BY episodes DESC
        """,
        cutoff=WINDOW_CUTOFF,
    )
    print("By bucket:")
    show(rows, 20)
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_referral, d_first_seen
        WHERE d_referral IS NOT NULL AND d_first_seen IS NULL
          AND d_referral <= date($cutoff)
          AND NOT coalesce(ep.status, '') IN ['closed_benign', 'merged']
          AND coalesce(ep.auto_closed, false) = false
        RETURN
            ep.patient_id AS pid,
            ep.cancer_type AS cancer,
            toString(d_referral) AS d_ref,
            ep.status AS status,
            ep.auto_close_reason AS reason,
            coalesce(ep.specialist_seen, '<null>') AS specialist_seen,
            toString(date(ep.specialist_visit_date)) AS specialist_visit
        ORDER BY pid
        LIMIT 15
        """,
        cutoff=WINDOW_CUTOFF,
    )
    print(
        "Sample of out-of-window unresolved cases (real candidates for missed-first-seen regex):"
    )
    show(rows, 15)


def q3_diagnosis_no_first_seen(c) -> None:
    header("Q3. Diagnosis WITHOUT a first-seen milestone (same episode)")
    print("Hypothesis: specialist contact exists but is called something else.")
    print("Show what specialist_seen / specialist_visit_date the episode carries,")
    print("plus the distinct anchor types present in the patient's window.")
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_first_seen, d_diagnosis
        WHERE d_diagnosis IS NOT NULL AND d_first_seen IS NULL
        RETURN
            coalesce(ep.specialist_seen, '<null>') AS specialist_seen,
            coalesce(ep.place_of_presentation, '<null>') AS place,
            count(DISTINCT ep) AS episodes,
            count(DISTINCT ep.patient_id) AS patients
        ORDER BY episodes DESC
        """,
    )
    print("By specialist_seen + place:")
    show(rows, 20)
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_diagnosis, d_first_seen
        WHERE d_diagnosis IS NOT NULL AND d_first_seen IS NULL
        OPTIONAL MATCH (enc:Encounter)
        WHERE enc.id IN [
            (e:Encounter)-[:IS_PART_OF]->(ep) | e.id
        ]
        WITH ep, d_diagnosis, collect(DISTINCT substring(coalesce(enc.text, ''), 0, 120))[0..3] AS sample_text
        RETURN
            ep.patient_id AS pid,
            ep.cancer_type AS cancer,
            toString(d_diagnosis) AS d_dx,
            sample_text
        ORDER BY pid
        LIMIT 8
        """,
    )
    print("Sample episodes with snippets of linked encounter text:")
    show(rows, 8)


def q4_treatment_no_diagnosis_90d(c) -> None:
    header("Q4. Treatment with NO diagnosis in the preceding 90 days")
    print("Hypothesis: continuation of an earlier cancer, or missed diagnosis regex.")
    print("Look 365 days back at any diagnosis anchor for the same patient.")
    print()

    rows = run(
        c,
        """
        MATCH (ep:EpisodeOfCare)
        MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
        WITH ep, min(date(e_tx.date)) AS d_tx
        WITH ep, d_tx WHERE d_tx IS NOT NULL
        OPTIONAL MATCH (e_dx_same:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
        WITH ep, d_tx, min(date(e_dx_same.date)) AS d_dx_same
        WITH ep, d_tx, d_dx_same
        WHERE d_dx_same IS NULL OR duration.between(d_dx_same, d_tx).days > 90 OR d_dx_same > d_tx
        OPTIONAL MATCH (ep_old:EpisodeOfCare {patient_id: ep.patient_id})
        WHERE ep_old.episode_id <> ep.episode_id
        OPTIONAL MATCH (e_dx_old:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep_old)
        WITH ep, d_tx, d_dx_same, max(date(e_dx_old.date)) AS d_dx_other
        WITH ep, d_tx, d_dx_same, d_dx_other,
             CASE
               WHEN d_dx_other IS NOT NULL
                    AND duration.between(d_dx_other, d_tx).days >= 0
                    AND duration.between(d_dx_other, d_tx).days <= 365
               THEN 'continuation_other_episode'
               WHEN d_dx_other IS NOT NULL AND d_dx_other < d_tx
               THEN 'historic_diagnosis_>365d'
               ELSE 'no_diagnosis_anywhere_for_patient'
             END AS bucket
        RETURN bucket, count(DISTINCT ep) AS episodes, count(DISTINCT ep.patient_id) AS patients
        ORDER BY episodes DESC
        """,
    )
    print("By bucket:")
    show(rows, 20)
    print()

    rows = run(
        c,
        """
        MATCH (ep:EpisodeOfCare)
        MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
        WITH ep, min(date(e_tx.date)) AS d_tx
        OPTIONAL MATCH (e_dx_same:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
        WITH ep, d_tx, min(date(e_dx_same.date)) AS d_dx_same
        WHERE d_tx IS NOT NULL
          AND (d_dx_same IS NULL OR duration.between(d_dx_same, d_tx).days > 90 OR d_dx_same > d_tx)
        RETURN
            ep.patient_id AS pid,
            ep.cancer_type AS cancer,
            toString(d_tx) AS d_tx,
            toString(d_dx_same) AS d_dx_same,
            ep.status AS status
        ORDER BY pid
        LIMIT 15
        """,
    )
    print("Sample episodes:")
    show(rows, 15)


def q5_diagnosis_no_treatment(c) -> None:
    header("Q5. Diagnosis WITHOUT treatment-started")
    print("Buckets: in-window (diagnosis after 2025-09-30), benign, or no-treatment-recorded.")
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_diagnosis, d_treatment
        WHERE d_diagnosis IS NOT NULL AND d_treatment IS NULL
        WITH ep, d_diagnosis,
             CASE
               WHEN d_diagnosis > date($cutoff) THEN 'in_window_under_90d_post_diag'
               WHEN ep.status = 'closed_benign' THEN 'closed_benign_with_diag_anchor'
               WHEN ep.status STARTS WITH 'stale' THEN 'auto_closed_stale'
               WHEN coalesce(ep.auto_closed, false) THEN 'auto_closed_other'
               ELSE 'no_treatment_recorded'
             END AS bucket
        RETURN bucket, count(DISTINCT ep) AS episodes, count(DISTINCT ep.patient_id) AS patients
        ORDER BY episodes DESC
        """,
        cutoff=WINDOW_CUTOFF,
    )
    print("By bucket:")
    show(rows, 20)
    print()

    rows = run(
        c,
        EP_VIEW
        + """
        WITH ep, d_diagnosis, d_treatment
        WHERE d_diagnosis IS NOT NULL AND d_treatment IS NULL
          AND d_diagnosis <= date($cutoff)
          AND ep.status <> 'closed_benign'
          AND coalesce(ep.auto_closed, false) = false
        RETURN
            ep.patient_id AS pid,
            ep.cancer_type AS cancer,
            toString(d_diagnosis) AS d_dx,
            ep.status AS status,
            coalesce(ep.inferred_outcome, '<null>') AS inferred_outcome
        ORDER BY pid
        LIMIT 12
        """,
        cutoff=WINDOW_CUTOFF,
    )
    print("Sample episodes (real 'diagnosed but no treatment recorded' candidates):")
    show(rows, 12)


def q_summary(c) -> None:
    header("Funnel summary -- distinct PATIENTS at each stage (all years)")
    rows = run(
        c,
        EP_VIEW
        + """
        WITH
          collect(DISTINCT CASE WHEN d_referral  IS NOT NULL THEN ep.patient_id END) AS p_ref,
          collect(DISTINCT CASE WHEN d_first_seen IS NOT NULL THEN ep.patient_id END) AS p_fs,
          collect(DISTINCT CASE WHEN d_diagnosis IS NOT NULL THEN ep.patient_id END) AS p_dx,
          collect(DISTINCT CASE WHEN d_treatment IS NOT NULL THEN ep.patient_id END) AS p_tx,
          collect(DISTINCT CASE
              WHEN ep.status = 'closed_benign'
                OR coalesce(ep.letter_inferred_benign, false) = true
              THEN ep.patient_id END) AS p_benign,
          count(DISTINCT ep.patient_id) AS p_any
        RETURN
          [x IN p_ref WHERE x IS NOT NULL | x] AS p_ref,
          [x IN p_fs  WHERE x IS NOT NULL | x] AS p_fs,
          [x IN p_dx  WHERE x IS NOT NULL | x] AS p_dx,
          [x IN p_tx  WHERE x IS NOT NULL | x] AS p_tx,
          [x IN p_benign WHERE x IS NOT NULL | x] AS p_benign,
          p_any
        """,
    )
    if not rows:
        return
    r = rows[0]
    print(f"  Patients with any episode  : {r['p_any']}")
    print(f"  ... reached referral       : {len(r['p_ref'])}")
    print(f"  ... reached first_seen     : {len(r['p_fs'])}")
    print(f"  ... reached diagnosis      : {len(r['p_dx'])}")
    print(f"  ... reached benign outcome : {len(r['p_benign'])}")
    print(f"  ... reached treatment      : {len(r['p_tx'])}")


def main() -> None:
    c = PatientGraphClient()
    try:
        q_summary(c)
        q1_no_referral(c)
        q2_referral_no_first_seen(c)
        q3_diagnosis_no_first_seen(c)
        q4_treatment_no_diagnosis_90d(c)
        q5_diagnosis_no_treatment(c)
    finally:
        c.close()


if __name__ == "__main__":
    main()
