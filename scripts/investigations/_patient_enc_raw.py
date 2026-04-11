"""Show raw encounter fields for patient 4203796334."""

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

Q = """
MATCH (enc:Encounter {patient_id: $pid})
RETURN
    enc.date                             AS date,
    enc.encounter_type                   AS etype,
    enc.classification_encounter_purpose AS purpose,
    enc.snomed_code                      AS snomed,
    enc.encounter_id                     AS eid
ORDER BY enc.date
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            rows = s.run(Q, pid=PATIENT_ID).data()
            print(f"Total encounters for {PATIENT_ID}: {len(rows)}")
            print()
            # group by year
            by_year: dict[str, list] = {}
            for r in rows:
                year = (r["date"] or "")[:4] or "unknown"
                by_year.setdefault(year, []).append(r)

            for year in sorted(by_year):
                enc_list = by_year[year]
                print(f"--- {year} ({len(enc_list)} encounters) ---")
                for r in enc_list:
                    print(
                        f"  {r['date'] or '?':12}  type={r['etype'] or '-':30}  "
                        f"purpose={r['purpose'] or '-':40}  snomed={r['snomed'] or '-'}"
                    )
    finally:
        client.close()


if __name__ == "__main__":
    main()
