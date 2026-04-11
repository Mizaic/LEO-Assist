"""Systematic SNOMED coding fixes -- no LLM needed.

Fix 1: Delete 'Normal appearance' (281900007) from all encounters.
  These were created from NAD surface form, which is now blocked.
  NAD is ambiguous (No Abnormality Detected vs No Apparent Distress)
  and our policy is to never code it.

Fix 2: Delete 'Seen in GP surgery' (185202000) from encounters where
  the encounter also has 'Telephone consultation' (185317003) coded,
  or the encounter text clearly indicates a phone/video call.
  Logically contradictory -- you cannot be seen in surgery on a phone call.

Prints counts before deleting. Requires --yes to commit.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

# -- Query: count NAD 'Normal appearance' codings ----------------------------
_Q_COUNT_NAD = """
MATCH ()-[r:DOCUMENTS]->(s {conceptId: 281900007})
RETURN count(r) AS cnt
"""

# -- Query: delete NAD 'Normal appearance' codings ---------------------------
_Q_DELETE_NAD = """
MATCH (e:Encounter)<-[:HAS_ENCOUNTER]-(p:Patient)
MATCH (e)-[r:DOCUMENTS]->(s {conceptId: 281900007})
DELETE r
WITH p, s
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e2)-[:DOCUMENTS]->(s)
WITH p, s, count(e2) AS remaining
FOREACH (_ IN CASE WHEN remaining = 0 THEN [1] ELSE [] END |
    SET s._needs_cleanup = true
)
RETURN count(*) AS deleted
"""

# -- Cleanup patient shortcuts for deleted concepts --------------------------
_Q_CLEANUP_NAD_SHORTCUTS = """
MATCH (p:Patient)-[pr]->(s {conceptId: 281900007})
WHERE type(pr) IN ['HAS_FINDING', 'HAS_DISORDER', 'HAS_CONCEPT']
DELETE pr
RETURN count(pr) AS shortcuts_removed
"""

# -- Count GP-surgery on phone consultations (logically contradictory) -------
_Q_COUNT_SURGERY_ON_PHONE = """
MATCH (e:Encounter)-[:DOCUMENTS]->(gp_surgery {conceptId: 185202000})
MATCH (e)-[:DOCUMENTS]->(tel {conceptId: 185317003})
RETURN count(DISTINCT e) AS cnt
"""

# -- Delete GP-surgery codes from phone consultations ------------------------
_Q_DELETE_SURGERY_ON_PHONE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(gp_surgery {conceptId: 185202000})
MATCH (e)-[:DOCUMENTS]->(tel {conceptId: 185317003})
DELETE r
RETURN count(r) AS deleted
"""

# -- Also catch text-based phone consultations (backup) ----------------------
_Q_COUNT_SURGERY_TEXT_PHONE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s {conceptId: 185202000})
WHERE (
    toLower(e.text) CONTAINS 'telephone consultation' OR
    toLower(e.text) CONTAINS 'phone consultation' OR
    toLower(e.text) CONTAINS 'telephone call' OR
    toLower(e.text) CONTAINS 'video consultation' OR
    toLower(e.text) CONTAINS 'video call'
)
RETURN count(r) AS cnt
"""

_Q_DELETE_SURGERY_TEXT_PHONE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s {conceptId: 185202000})
WHERE (
    toLower(e.text) CONTAINS 'telephone consultation' OR
    toLower(e.text) CONTAINS 'phone consultation' OR
    toLower(e.text) CONTAINS 'telephone call' OR
    toLower(e.text) CONTAINS 'video consultation' OR
    toLower(e.text) CONTAINS 'video call'
)
DELETE r
RETURN count(r) AS deleted
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Systematic coding fixes (no LLM)")
    p.add_argument(
        "--yes", action="store_true", help="Commit deletes (default dry-run)"
    )
    args = p.parse_args()

    client = PatientGraphClient()
    try:
        with client.session() as session:
            nad_cnt = session.run(_Q_COUNT_NAD).single()["cnt"]
            surg_phone_cnt = session.run(_Q_COUNT_SURGERY_ON_PHONE).single()["cnt"]
            surg_text_cnt = session.run(_Q_COUNT_SURGERY_TEXT_PHONE).single()["cnt"]

        print("=== SYSTEMATIC FIX PREVIEW ===")
        print(f"  NAD 'Normal appearance' (281900007) to delete   : {nad_cnt:,}")
        print(f"  'Seen in GP surgery' on phone (coded)           : {surg_phone_cnt:,}")
        print(f"  'Seen in GP surgery' on phone (text)            : {surg_text_cnt:,}")
        print()

        if not args.yes:
            print("Run with --yes to commit these deletes.")
            return

        with client.session() as session:
            nad_del = session.run(_Q_DELETE_NAD).single()["deleted"]
            nad_sc = session.run(_Q_CLEANUP_NAD_SHORTCUTS).single()["shortcuts_removed"]
            surg_del_a = session.run(_Q_DELETE_SURGERY_ON_PHONE).single()["deleted"]
            surg_del_b = session.run(_Q_DELETE_SURGERY_TEXT_PHONE).single()["deleted"]

        print("=== APPLIED ===")
        print(f"  NAD documents deleted        : {nad_del:,}")
        print(f"  NAD patient shortcuts removed: {nad_sc:,}")
        print(f"  GP-surgery phone (coded)     : {surg_del_a:,}")
        print(f"  GP-surgery phone (text)      : {surg_del_b:,}")
        print(f"  Total deletes                : {nad_del + surg_del_a + surg_del_b:,}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
