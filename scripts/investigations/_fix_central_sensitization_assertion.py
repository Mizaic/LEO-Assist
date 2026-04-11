"""Fix wrong 'present' assertion on Central sensitization for encounter f3308afb.

The note says 'Likely some central sensitisation' which should be 'possible'.
The DOCUMENTS edge was written before context JSON was supported (ctx=None).
We set context JSON and audit_flag directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

pg_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
pg_user = os.getenv("NEO4J_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "patient-dev")

CONTEXT_POSSIBLE = (
    '{"assertion": "possible", "negated": false, '
    '"uncertain": true, "historical": false, '
    '"hypothetical": false, "family": false}'
)

FIX_Q = """
MATCH (e:Encounter {id: $eid})-[r:DOCUMENTS]->(n {conceptId: $cid})
SET r.context = $ctx,
    r.audit_flag = 'assertion_corrected_v3_likely_some'
RETURN count(r) AS updated
"""


def main() -> None:
    driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))
    try:
        with driver.session() as s:
            res = s.run(
                FIX_Q,
                eid="f3308afb-9f43-41d4-99d8-a6cd7f9a6743",
                cid="789494008",
                ctx=CONTEXT_POSSIBLE,
            ).single()
            updated = res["updated"] if res else 0
            if updated:
                print(f"OK -- updated {updated} DOCUMENTS edge(s).")
                print("  Central sensitization (789494008) now assertion=possible.")
            else:
                print(
                    "No matching edge found -- already corrected or encounter absent."
                )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
