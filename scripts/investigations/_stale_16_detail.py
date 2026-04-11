"""Detail view of the 16 'Referral + Specialist only' patients: referral concept/date + post-referral encounter count."""

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

# Patients who have at least one episode with specialist_seen AND no cancer_diagnosis on any episode
# These are the "Referral + Specialist only" patients
_Q_PATIENTS = """
MATCH (ep:EpisodeOfCare)
WHERE ep.specialist_seen = true
  AND ep.status = 'stale_post_specialist'
WITH ep.patient_id AS pid, ep.referral_date AS ref_date,
     ep.specialist_visit_date AS visit_date,
     ep.cancer_type AS site,
     ep.status AS status
RETURN DISTINCT pid, site, ref_date, visit_date, status
ORDER BY ref_date DESC
"""

# Referral concept: find the concept linked to the referral anchor for this patient/episode
_Q_REF_CONCEPT = """
MATCH (ep:EpisodeOfCare {patient_id: $pid, referral_date: $ref_date})
      <-[:IS_PART_OF]-(enc:Encounter)-[:DOCUMENTS]->(c)
OPTIONAL MATCH (c)-[:IS_A]->(parent)
RETURN DISTINCT c.name AS concept_name
LIMIT 1
"""

# Post-referral encounter count: encounters with date >= ref_date using string comparison (ISO dates sort lexically)
_Q_ENC_AFTER = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $ref_date
RETURN count(enc) AS enc_after
"""

# What concepts were encountered after referral (to help understand if diagnosis was missed)
_Q_POST_CONCEPTS = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE enc.date >= $ref_date
RETURN DISTINCT c.name AS name, enc.date AS enc_date
ORDER BY enc_date DESC
LIMIT 5
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            patients = s.run(_Q_PATIENTS).data()
            print(f"stale_post_specialist episodes: {len(patients)}")
            print()
            header = f"{'#':<3} {'Site':<18} {'Ref date':<12} {'Visit date':<12} {'Enc after':>10}  Referral concept"
            print(header)
            print("-" * 110)

            for i, row in enumerate(patients, 1):
                pid = str(row["pid"])
                ref_date = str(row["ref_date"] or "")
                site = str(row["site"] or "unknown")
                visit_date = str(row["visit_date"] or "N/A")

                enc_row = s.run(_Q_ENC_AFTER, pid=pid, ref_date=ref_date).single()
                enc_after = enc_row["enc_after"] if enc_row else 0

                concept_row = s.run(_Q_REF_CONCEPT, pid=pid, ref_date=ref_date).single()
                concept = (concept_row["concept_name"] if concept_row else "") or ""
                if len(concept) > 55:
                    concept = concept[:52] + "..."

                print(
                    f"{i:<3} {site:<18} {ref_date:<12} {visit_date:<12} {enc_after:>10}  {concept}"
                )

                if enc_after > 0:
                    post = s.run(_Q_POST_CONCEPTS, pid=pid, ref_date=ref_date).data()
                    for p in post:
                        name = str(p["name"] or "")[:70]
                        print(f"    {str(p['enc_date']):<12} {name}")

            print()
            print("enc_after = encounters (any concept) on or after referral date")
    finally:
        client.close()


if __name__ == "__main__":
    main()
