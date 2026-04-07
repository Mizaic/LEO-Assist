"""Detail view of stale_post_specialist episodes: referral, visit, and post-referral encounter counts."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

# All stale_post_specialist episodes with referral concept, dates, visit info
_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'stale_post_specialist'
RETURN
  ep.patient_id            AS pid,
  ep.cancer_type           AS site,
  ep.referral_date         AS ref_date,
  ep.specialist_visit_date AS visit_date,
  ep.end_date              AS end_date,
  duration.inDays(date(ep.referral_date), date()).days AS days_since_ref,
  duration.inDays(date(ep.specialist_visit_date), date()).days AS days_since_visit
ORDER BY ep.referral_date DESC
"""

# Count encounters after referral date for each patient
_Q_ENC_AFTER = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.date >= date($ref_date)
RETURN count(e) AS enc_after
"""

# Get the referral concept name from the episode IS_PART_OF links
_Q_REF_CONCEPT = """
MATCH (ep:EpisodeOfCare {patient_id: $pid, referral_date: $ref_date})<-[r:IS_PART_OF]-(e:Encounter)-[:DOCUMENTS]->(c)
WHERE r.milestone_type = 'referral'
RETURN DISTINCT c.name AS concept_name
LIMIT 1
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            episodes = s.run(_Q_EPISODES).data()
            print(f"stale_post_specialist episodes: {len(episodes)}")
            print()
            print(f"{'Site':<20} {'Ref date':<12} {'Visit date':<12} {'Days/ref':>8} {'Days/vis':>8} {'Enc after':>10}  Referral concept")
            print("-" * 110)
            for ep in episodes:
                pid = ep["pid"]
                ref_date = str(ep["ref_date"] or "")

                enc_row = s.run(_Q_ENC_AFTER, pid=str(pid), ref_date=ref_date).single()
                enc_after = enc_row["enc_after"] if enc_row else 0

                concept_row = s.run(_Q_REF_CONCEPT, pid=str(pid), ref_date=ref_date).single()
                concept = (concept_row["concept_name"] if concept_row else "") or ""
                # Trim long concept names
                if len(concept) > 60:
                    concept = concept[:57] + "..."

                print(
                    f"{str(ep['site']):<20} "
                    f"{ref_date:<12} "
                    f"{str(ep['visit_date'] or 'N/A'):<12} "
                    f"{str(ep['days_since_ref'] or '?'):>8} "
                    f"{str(ep['days_since_visit'] or '?'):>8} "
                    f"{enc_after:>10}  "
                    f"{concept}"
                )
            print()
            print("Key: Days/ref = days since referral, Days/vis = days since specialist visit, Enc after = encounters on/after referral date")
    finally:
        client.close()


if __name__ == "__main__":
    main()
