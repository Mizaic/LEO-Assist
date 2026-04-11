"""Find the cystoscopy follow-up encounter for patient enc 18666e26.

The original audit encounter (18666e26-13ec-47fb-a5aa-b05840f06acb) recorded
"patient going for a cystoscopy on Tuesday under Urology". The agent proposed
adding a cystoscopy code with assertion=present, which Sonnet disputed because
the procedure had not yet occurred.

This script:
1. Looks up the patient ID for that encounter.
2. Searches for any later encounters mentioning cystoscopy.
3. Checks if a cystoscopy SNOMED code is already on the patient record.
4. Reports what action (if any) is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Load secrets before importing any client.
from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(_ROOT / "secrets" / ".env.config", override=False)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

ORIG_ENCOUNTER_ID = "18666e26-13ec-47fb-a5aa-b05840f06acb"

_Q_ENCOUNTER_PATIENT = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(e.id) = $enc_id OR e.id = $enc_id
RETURN toString(p.id) AS patient_id, e.date AS enc_date LIMIT 1
"""

_Q_LATER_ENCOUNTERS = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid AND e.date > $enc_date
RETURN toString(e.id) AS encounter_id, e.date AS date,
       coalesce(e.text, '') AS text
ORDER BY e.date ASC LIMIT 20
"""

_Q_CODED_CYSTOSCOPY = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = $pid
  AND toLower(s.name) CONTAINS 'cystoscop'
RETURN toString(e.id) AS encounter_id, e.date AS enc_date,
       s.conceptId AS concept_id, s.name AS name, r.context AS assertion
ORDER BY e.date DESC LIMIT 10
"""

_CYSTOSCOPY_KEYWORDS = ["cystoscop"]


def _mentions_cystoscopy(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _CYSTOSCOPY_KEYWORDS)


def main() -> None:
    try:
        from libs.neo4j_client.client import PatientGraphClient
    except ImportError:
        print("ERROR: cannot import PatientGraphClient -- run from project root.")
        sys.exit(1)

    client = PatientGraphClient()

    rows = client.run(_Q_ENCOUNTER_PATIENT, enc_id=ORIG_ENCOUNTER_ID)
    if not rows:
        print(f"ERROR: encounter {ORIG_ENCOUNTER_ID} not found in Neo4j.")
        client.close()
        sys.exit(1)

    patient_id = rows[0]["patient_id"]
    enc_date = rows[0]["enc_date"]
    print(f"Patient:          {patient_id}")
    print(f"Original enc date: {enc_date}")
    print()

    coded_rows = client.run(_Q_CODED_CYSTOSCOPY, pid=patient_id)
    historical_codes = [r for r in coded_rows if str(r["enc_date"]) < str(enc_date)]
    post_codes = [r for r in coded_rows if str(r["enc_date"]) >= str(enc_date)]

    if historical_codes:
        print("Historical cystoscopy codes (before planning encounter):")
        for r in historical_codes:
            print(
                f"  [{r['concept_id']}] {r['name']} | enc={r['encounter_id']}"
                f" date={r['enc_date']} assertion={r['assertion']}"
            )
        print()

    if post_codes:
        print("Cystoscopy coded on or AFTER the planning encounter:")
        for r in post_codes:
            print(
                f"  [{r['concept_id']}] {r['name']} | enc={r['encounter_id']}"
                f" date={r['enc_date']} assertion={r['assertion']}"
            )
        print()
        print("No action needed -- post-procedure cystoscopy already coded.")
        client.close()
        return

    print("Planned cystoscopy from Dec 2025 NOT yet coded post-procedure.")
    print()

    later = client.run(_Q_LATER_ENCOUNTERS, pid=patient_id, enc_date=enc_date)
    matches = [r for r in later if _mentions_cystoscopy(r.get("text", ""))]

    if matches:
        print(f"Found {len(matches)} later encounter(s) mentioning cystoscopy:")
        for r in matches:
            snippet = r["text"][:200].replace("\n", " ")
            print(f"  enc={r['encounter_id']} date={r['date']}")
            print(f"    {snippet}")
        print()
        print("RECOMMENDATION: Re-run the audit agent on these encounters.")
        print("The cystoscopy should be coded on the POST-procedure encounter,")
        print("not on the planning encounter (18666e26).")
    else:
        print("No post-procedure encounter found in imported data.")
        print()
        print("RECOMMENDATION: No action on 18666e26 (planning-only encounter).")
        print("Code the cystoscopy on the post-procedure encounter when imported.")

    client.close()

    result = {
        "patient_id": patient_id,
        "original_encounter_id": ORIG_ENCOUNTER_ID,
        "original_enc_date": str(enc_date),
        "historical_cystoscopy_codes": len(historical_codes),
        "post_procedure_coded": bool(post_codes),
        "later_encounters_with_cystoscopy": [
            {"encounter_id": r["encounter_id"], "date": str(r["date"])} for r in matches
        ],
    }
    print()
    print("JSON summary:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
