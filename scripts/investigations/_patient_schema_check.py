"""Check encounter node schema and how patient 4203796334 is stored."""

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

PATIENT_ID = "4203796334"


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            # What keys does an Encounter node have?
            enc_keys = s.run("MATCH (e:Encounter) RETURN keys(e) AS k LIMIT 1").data()
            print("Encounter keys:", enc_keys[0]["k"] if enc_keys else "NO ENCOUNTERS")

            # Check the EpisodeOfCare node for this patient to confirm property name
            ep_rows = s.run(
                "MATCH (ep:EpisodeOfCare {patient_id: $pid}) RETURN ep LIMIT 1",
                pid=PATIENT_ID,
            ).data()
            print(
                f"\nEpisode node (patient_id={PATIENT_ID}):",
                "FOUND" if ep_rows else "NOT FOUND",
            )
            if ep_rows:
                ep = dict(ep_rows[0]["ep"])
                print("  episode keys:", sorted(ep.keys()))

            # How is the encounter linked to the episode for this patient?
            linked = s.run(
                """
                MATCH (ep:EpisodeOfCare {patient_id: $pid})<-[:IS_PART_OF]-(enc:Encounter)
                RETURN keys(enc) AS ek, enc LIMIT 1
            """,
                pid=PATIENT_ID,
            ).data()
            if linked:
                enc = dict(linked[0]["enc"])
                print("\nLinked encounter keys:", sorted(enc.keys()))
                print("Sample encounter props:")
                for k in sorted(enc.keys()):
                    print(f"  {k}: {enc[k]}")
            else:
                print("\nNo linked encounters via IS_PART_OF for this patient")

                # Try finding encounters a different way
                enc_via_patient = s.run(
                    """
                    MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
                    WHERE p.patient_id = $pid OR p.id = $pid OR p.nhs_number = $pid
                    RETURN enc LIMIT 1
                """,
                    pid=PATIENT_ID,
                ).data()
                print(
                    "Encounters via Patient->HAS_ENCOUNTER:",
                    "FOUND" if enc_via_patient else "not found",
                )

                # Try all encounters and check patient link
                any_enc = s.run(
                    "MATCH (enc:Encounter) RETURN keys(enc) AS k, enc LIMIT 1"
                ).data()
                if any_enc:
                    enc = dict(any_enc[0]["enc"])
                    print("\nSample ANY encounter keys:", sorted(enc.keys()))
                    for k in sorted(enc.keys()):
                        print(f"  {k}: {enc[k]}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
