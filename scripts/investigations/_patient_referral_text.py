"""Show full encounter text for referral-date encounters for patient 4203796334."""
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

# Dates that correspond to episode referral_dates or clinic letters
REFERRAL_DATES = {
    "2024-08-05",  # ep 218c363 referral
    "2024-08-30",  # clinic letter UHL Derm (back-dated)
    "2024-09-16",  # ep fda1920 referral / specialist
    "2025-07-18",  # letter (back-dated Jul 2025)
    "2025-07-21",  # ep df4b199 referral
    "2025-08-04",  # ep 5df35c0 + bff2d6a referrals
    "2025-08-05",  # clinic letter (back-dated Aug 2025)
}

Q = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date IN $dates
RETURN enc.id AS enc_id, enc.date AS date, enc.flags AS flags, enc.text AS text
ORDER BY enc.date, enc.id
"""


def _divider(char: str = "-", width: int = 80) -> str:
    return char * width


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            rows = s.run(Q, pid=PATIENT_ID, dates=list(REFERRAL_DATES)).data()
            print(f"=== Referral-date encounters for patient {PATIENT_ID} ===")
            print(f"    {len(rows)} encounters on {len(REFERRAL_DATES)} target dates\n")

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
                print(_divider())
                print(text)
                print(_divider())
    finally:
        client.close()


if __name__ == "__main__":
    main()
