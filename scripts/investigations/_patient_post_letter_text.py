"""All encounter text for patient 4203796334 in the 90 days after 2024-08-30."""

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
FROM_DATE = "2024-08-30"
TO_DATE = "2024-11-28"  # 90 days later

Q = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $from_date AND enc.date <= $to_date
RETURN enc.id AS enc_id, enc.date AS date, enc.flags AS flags, enc.text AS text
ORDER BY enc.date, enc.id
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            rows = s.run(Q, pid=PATIENT_ID, from_date=FROM_DATE, to_date=TO_DATE).data()
            print(
                f"=== Patient {PATIENT_ID} -- {FROM_DATE} to {TO_DATE} ({len(rows)} encounters) ===\n"
            )

            cur_date = None
            for r in rows:
                if r["date"] != cur_date:
                    cur_date = r["date"]
                    print(f"\n{'=' * 80}")
                    print(f"  DATE: {cur_date}")
                    print(f"{'=' * 80}")

                flags = (r["flags"] or "").strip()
                text = (r["text"] or "").strip()
                enc_id = r["enc_id"] or "?"

                print(f"\n  [{enc_id}]")
                print(f"  FLAGS : {flags[:120]}")
                print("-" * 80)
                print(text)
                print("-" * 80)
    finally:
        client.close()


if __name__ == "__main__":
    main()
