"""Breakdown of referrals, specialist visits, and diagnoses by year for patient 4203796334."""

from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

PATIENT_ID = "4203796334"

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare {patient_id: $pid})
RETURN
    ep.episode_id            AS episode_id,
    ep.status                AS status,
    ep.cancer_type           AS cancer_type,
    ep.referral_date         AS referral_date,
    ep.specialist_seen       AS specialist_seen,
    ep.specialist_visit_date AS specialist_visit_date,
    ep.hitl_flag             AS hitl_flag,
    ep.end_date              AS end_date
ORDER BY ep.referral_date
"""

# Encounters reached via the Patient node
_Q_ENCOUNTERS = """
MATCH (p:Patient {patient_id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
OPTIONAL MATCH (enc)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
RETURN
    enc.id        AS enc_id,
    enc.date      AS date,
    enc.flags     AS flags,
    r.milestone_type  AS milestone,
    ep.episode_id AS episode_id,
    ep.cancer_type AS cancer_type
ORDER BY enc.date
"""

# Also check alternate patient linkage
_Q_ENCOUNTERS_ALT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE p.id = $pid OR p.patient_id = $pid OR p.nhs_number = $pid
OPTIONAL MATCH (enc)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
RETURN
    enc.id        AS enc_id,
    enc.date      AS date,
    enc.flags     AS flags,
    r.milestone_type  AS milestone,
    ep.episode_id AS episode_id,
    ep.cancer_type AS cancer_type
ORDER BY enc.date
"""

# Check Patient node properties
_Q_PATIENT = """
MATCH (p:Patient)
WHERE p.patient_id = $pid OR p.id = $pid
RETURN keys(p) AS k, p LIMIT 1
"""


def _classify_flags(flags: str | None) -> str:
    if not flags:
        return "unknown"
    f = flags.lower()
    if "referral" in f or "2ww" in f or "fast" in f:
        return "referral"
    if (
        "specialist" in f
        or "outpatient" in f
        or "clinic letter" in f
        or "clinic_letter" in f
    ):
        return "specialist"
    if "diagnosis" in f or "cancer" in f:
        return "diagnosis"
    return "other"


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            print(f"=== Patient {PATIENT_ID} ===\n")

            # Find the Patient node
            pat_rows = s.run(_Q_PATIENT, pid=PATIENT_ID).data()
            if pat_rows:
                pat = dict(pat_rows[0]["p"])
                print(f"Patient node keys: {sorted(pat.keys())}")
                print(
                    f"Patient props: { {k: v for k, v in pat.items() if k != 'vector'} }\n"
                )
            else:
                print(f"WARNING: No Patient node found for id={PATIENT_ID}\n")

            # Episodes
            episodes = s.run(_Q_EPISODES, pid=PATIENT_ID).data()
            print(f"EPISODES ({len(episodes)} total):")
            print(
                f"{'ID':<20} {'Status':<25} {'Type':<12} {'Referral':<12} {'Specialist':<12} {'End':<12} {'HITL'}"
            )
            print("-" * 110)
            for ep in episodes:
                print(
                    f"{ep['episode_id'] or '-':<20} "
                    f"{ep['status'] or '-':<25} "
                    f"{ep['cancer_type'] or '-':<12} "
                    f"{ep['referral_date'] or '-':<12} "
                    f"{ep['specialist_visit_date'] or '-':<12} "
                    f"{ep['end_date'] or '-':<12} "
                    f"{ep['hitl_flag'] or '-'}"
                )

            # Try primary encounter query, fallback to alt
            enc_rows = s.run(_Q_ENCOUNTERS, pid=PATIENT_ID).data()
            if not enc_rows:
                print(f"\nNo encounters via patient_id, trying alt...\n")
                enc_rows = s.run(_Q_ENCOUNTERS_ALT, pid=PATIENT_ID).data()

            print(f"\nENCOUNTERS ({len(enc_rows)} total):\n")

            if not enc_rows:
                print("  No encounters found. Checking raw encounter link...")
                # Try IS_PART_OF from episodes directly
                milestone_rows = s.run(
                    """
                    MATCH (ep:EpisodeOfCare {patient_id: $pid})<-[r:IS_PART_OF]-(enc:Encounter)
                    RETURN enc.id AS enc_id, enc.date AS date, enc.flags AS flags,
                           r.milestone_type AS milestone, ep.episode_id AS episode_id,
                           ep.cancer_type AS cancer_type
                    ORDER BY enc.date
                """,
                    pid=PATIENT_ID,
                ).data()
                print(
                    f"  Via IS_PART_OF from episodes: {len(milestone_rows)} encounters"
                )
                enc_rows = milestone_rows

            # Group by year
            def _new_year_bucket() -> dict:
                return {
                    "referral": 0,
                    "specialist": 0,
                    "diagnosis": 0,
                    "milestone": 0,
                    "other": 0,
                    "unknown": 0,
                }

            by_year: dict[str, dict] = defaultdict(_new_year_bucket)
            milestone_rows = []

            for r in enc_rows:
                year = (r.get("date") or "")[:4] or "unknown"
                flags = r.get("flags") or ""
                milestone = r.get("milestone")

                if milestone:
                    milestone_rows.append(r)
                    by_year[year]["milestone"] += 1

                cat = _classify_flags(flags)
                by_year[year][cat] += 1

            # Year summary
            print(f"COUNTS BY YEAR (based on flags classification):")
            print(
                f"{'Year':<6} {'Referral':>8} {'Specialist':>10} {'Diagnosis':>10} {'Other':>6} {'Milestone-linked':>17}"
            )
            print("-" * 60)
            for year in sorted(by_year):
                d = by_year[year]
                print(
                    f"{year:<6} "
                    f"{d['referral']:>8} "
                    f"{d['specialist']:>10} "
                    f"{d['diagnosis']:>10} "
                    f"{d['other']:>6} "
                    f"{d['milestone']:>17}"
                )

            # Milestone encounters detail
            if milestone_rows:
                print(f"\nMILESTONE-LINKED ENCOUNTERS ({len(milestone_rows)}):")
                print(
                    f"{'Date':<12} {'Milestone':<25} {'Episode':<20} {'Cancer':<12} {'Flags (first 60)'}"
                )
                print("-" * 110)
                for r in sorted(milestone_rows, key=lambda x: x.get("date") or ""):
                    flags_short = (r.get("flags") or "")[:60].replace("\n", " ")
                    print(
                        f"{r.get('date') or '-':<12} "
                        f"{r.get('milestone') or '-':<25} "
                        f"{r.get('episode_id') or '-':<20} "
                        f"{r.get('cancer_type') or '-':<12} "
                        f"{flags_short}"
                    )

            # Full encounter list per year
            print(f"\nALL ENCOUNTERS BY YEAR:")
            cur_year = None
            for r in enc_rows:
                year = (r.get("date") or "")[:4] or "unknown"
                if year != cur_year:
                    cur_year = year
                    print(f"\n  -- {year} --")
                flags_short = (r.get("flags") or "")[:80].replace("\n", " ")
                milestone = r.get("milestone") or ""
                ep_id = (r.get("episode_id") or "")[-8:]
                print(
                    f"  {r.get('date') or '?':12}  "
                    f"milestone={milestone or '-':20}  "
                    f"ep={ep_id or '-':10}  "
                    f"{flags_short}"
                )

    finally:
        client.close()


if __name__ == "__main__":
    main()
