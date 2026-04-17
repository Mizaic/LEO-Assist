"""Follow-up investigation -- five things the first sweep flagged.

1. Every sample episode is cancer_type=non_site_specific. Is that the full
   distribution, or is the site-classifier producing it almost everywhere?
2. Every sample has referral_route='other'. Is route detection working at all?
3. PRISM 2WW questionnaire encounters appear to be missing from referral
   anchors -- check the patient who showed this in Q3 (4203796334).
4. Treatment-before-diagnosis pattern: are treatment anchors firing on
   non-cancer medications? Pull the encounter text for the offending dates.
5. Q4 bucketing was confusing -- re-run with the proper buckets:
   tx_before_same_episode_dx, tx_before_other_episode_dx,
   no_diagnosis_anywhere.
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


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def show(rows, limit: int = 12) -> None:
    if not rows:
        print("  (no rows)")
        return
    for r in rows[:limit]:
        print("  ", dict(r))
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more")


def q1_cancer_type(c) -> None:
    header("FU-1. cancer_type distribution across all 230 episodes")
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare)
            RETURN coalesce(ep.cancer_type, '<null>') AS cancer_type,
                   count(ep) AS episodes
            ORDER BY episodes DESC
            """
        ),
        30,
    )


def q2_referral_route(c) -> None:
    header("FU-2. referral_route + place_of_presentation distribution")
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare)
            RETURN coalesce(ep.referral_route, '<null>') AS route,
                   coalesce(ep.place_of_presentation, '<null>') AS place,
                   count(ep) AS episodes
            ORDER BY episodes DESC
            """
        ),
        30,
    )


def q3_prism_check(c) -> None:
    header("FU-3. patient 4203796334 -- PRISM 2WW dermatology not detected as referral?")
    print("Show every encounter for this patient with PRISM-2WW or fast-track text.")
    show(
        c.run(
            """
            MATCH (p:Patient {id: '4203796334'})-[:HAS_ENCOUNTER]->(e:Encounter)
            WHERE toLower(e.text) CONTAINS 'prism'
               OR toLower(e.text) CONTAINS 'fast track'
               OR toLower(e.text) CONTAINS 'fast-track'
               OR toLower(e.text) CONTAINS '2ww'
            RETURN e.id AS eid,
                   toString(date(e.date)) AS d,
                   substring(e.text, 0, 220) AS snippet
            ORDER BY date(e.date)
            """
        ),
        15,
    )
    print()
    print("Episodes for this patient and their milestone dates:")
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare {patient_id: '4203796334'})
            OPTIONAL MATCH (e_ref:Encounter)-[:IS_PART_OF {milestone_type: 'referral'}]->(ep)
            WITH ep, min(date(e_ref.date)) AS d_referral
            OPTIONAL MATCH (e_fs:Encounter)-[:IS_PART_OF {milestone_type: 'first_seen'}]->(ep)
            WITH ep, d_referral, min(date(e_fs.date)) AS d_first_seen
            OPTIONAL MATCH (e_dx:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
            WITH ep, d_referral, d_first_seen, min(date(e_dx.date)) AS d_diagnosis
            RETURN ep.episode_id AS ep, ep.cancer_type AS cancer, ep.status AS status,
                   toString(d_referral) AS d_ref,
                   toString(d_first_seen) AS d_fs,
                   toString(d_diagnosis) AS d_dx
            ORDER BY ep
            """
        )
    )


def q4_treatment_text(c) -> None:
    header("FU-4. Treatment anchors firing BEFORE diagnosis -- show encounter text")
    print("Pick the patient/date pairs where treatment fires months before diagnosis.")
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare)
            MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
            WITH ep, e_tx, date(e_tx.date) AS d_tx
            OPTIONAL MATCH (e_dx:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
            WITH ep, e_tx, d_tx, min(date(e_dx.date)) AS d_dx
            WHERE d_dx IS NOT NULL AND d_dx > d_tx
            RETURN
                ep.patient_id AS pid,
                toString(d_tx) AS d_tx,
                toString(d_dx) AS d_dx,
                duration.between(d_tx, d_dx).days AS gap_days,
                substring(e_tx.text, 0, 220) AS tx_snippet
            ORDER BY gap_days DESC
            """
        ),
        15,
    )


def q5_tx_no_dx_buckets(c) -> None:
    header(
        "FU-5. Treatment vs diagnosis -- corrected buckets"
    )
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare)
            MATCH (e_tx:Encounter)-[:IS_PART_OF {milestone_type: 'treatment_started'}]->(ep)
            WITH ep, min(date(e_tx.date)) AS d_tx
            OPTIONAL MATCH (e_dx_same:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
            WITH ep, d_tx, min(date(e_dx_same.date)) AS d_dx_same
            OPTIONAL MATCH (ep2:EpisodeOfCare {patient_id: ep.patient_id})
                <-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]-(:Encounter)
            WHERE ep2.episode_id <> ep.episode_id
            OPTIONAL MATCH (e_dx_other:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep2)
            WITH ep, d_tx, d_dx_same, max(date(e_dx_other.date)) AS d_dx_other_max
            WITH ep, d_tx, d_dx_same, d_dx_other_max,
                 CASE
                   WHEN d_dx_same IS NOT NULL
                        AND d_dx_same <= d_tx
                        AND duration.between(d_dx_same, d_tx).days <= 90
                   THEN 'tx_within_90d_of_same_dx'
                   WHEN d_dx_same IS NOT NULL
                        AND d_dx_same <= d_tx
                   THEN 'tx_more_than_90d_after_same_dx'
                   WHEN d_dx_same IS NOT NULL AND d_dx_same > d_tx
                   THEN 'tx_BEFORE_same_episode_dx'
                   WHEN d_dx_other_max IS NOT NULL
                        AND d_dx_other_max <= d_tx
                        AND duration.between(d_dx_other_max, d_tx).days <= 365
                   THEN 'tx_continuation_other_episode'
                   WHEN d_dx_other_max IS NOT NULL
                   THEN 'tx_with_dx_in_other_episode_unusual_timing'
                   ELSE 'tx_with_no_dx_anywhere'
                 END AS bucket
            RETURN bucket,
                   count(DISTINCT ep) AS episodes,
                   count(DISTINCT ep.patient_id) AS patients
            ORDER BY episodes DESC
            """
        ),
        20,
    )


def q6_first_seen_text_for_diag_no_fs(c) -> None:
    header(
        "FU-6. Diagnosis-no-first-seen -- pull encounter text containing clinic/specialist words"
    )
    print(
        "If a true clinic visit text exists, _RE_FIRST_SEEN is missing it."
    )
    show(
        c.run(
            """
            MATCH (ep:EpisodeOfCare)
            MATCH (e_dx:Encounter)-[:IS_PART_OF {milestone_type: 'diagnosis_confirmed'}]->(ep)
            WITH ep, min(date(e_dx.date)) AS d_dx
            OPTIONAL MATCH (e_fs:Encounter)-[:IS_PART_OF {milestone_type: 'first_seen'}]->(ep)
            WITH ep, d_dx, count(e_fs) AS n_fs WHERE n_fs = 0
            MATCH (p:Patient {id: ep.patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
            WHERE date(e.date) >= d_dx - duration({days: 60})
              AND date(e.date) <= d_dx
              AND (toLower(e.text) CONTAINS 'clinic'
                   OR toLower(e.text) CONTAINS 'consultant'
                   OR toLower(e.text) CONTAINS 'outpatient'
                   OR toLower(e.text) CONTAINS 'opd'
                   OR toLower(e.text) CONTAINS 'fast track'
                   OR toLower(e.text) CONTAINS 'fast-track'
                   OR toLower(e.text) CONTAINS 'reviewed in'
                   OR toLower(e.text) CONTAINS 'discussed in mdt'
                   OR toLower(e.text) CONTAINS 'attended'
                   OR toLower(e.text) CONTAINS 'seen by')
            RETURN ep.patient_id AS pid,
                   toString(d_dx) AS d_dx,
                   toString(date(e.date)) AS d_enc,
                   substring(e.text, 0, 220) AS snippet
            ORDER BY pid, d_enc
            """
        ),
        15,
    )


def main() -> None:
    c = PatientGraphClient()
    try:
        q1_cancer_type(c)
        q2_referral_route(c)
        q3_prism_check(c)
        q4_treatment_text(c)
        q5_tx_no_dx_buckets(c)
        q6_first_seen_text_for_diag_no_fs(c)
    finally:
        c.close()


if __name__ == "__main__":
    main()
