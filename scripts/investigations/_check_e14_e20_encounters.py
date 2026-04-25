"""Quick lookup of encounter IDs and coded concepts for E14 and E20 patients."""

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

Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) IN $pids
  AND toString(e.date) >= $after
RETURN
    toString(p.id)   AS pid,
    toString(e.id)   AS enc_id,
    toString(e.date) AS enc_date,
    c.conceptId      AS cid,
    c.name           AS cname,
    c.semanticTag    AS tag
ORDER BY pid, enc_date
"""

Q_CONCEPT = """
MATCH (c:Concept)
WHERE c.conceptId IN $cids
RETURN c.conceptId AS cid, c.name AS name, c.semanticTag AS tag
"""

client = PatientGraphClient()
with client.session() as s:
    print("=== Encounters with DOCUMENTS (2024+) for E14 and E20 patients ===")
    rows = list(s.run(Q, pids=["9990002008", "9990002009"], after="2024-01-01"))
    for r in rows:
        cname = (r["cname"] or "")[:50]
        print(
            f"  pid={r['pid']}  {r['enc_date']}  enc={r['enc_id'][:12]}  {r['cid']}  {cname}"
        )

    print()
    print("=== Checking if cancer concept nodes exist in KG ===")
    check_ids = [254838004, 363346000, 402815007, 372130007, 93761005, 448977009]
    rows2 = list(s.run(Q_CONCEPT, cids=check_ids))
    if rows2:
        for r in rows2:
            print(f"  FOUND: {r['cid']}  {r['name']}  ({r['tag']})")
    else:
        print("  None of the target concept IDs found as Concept nodes.")

client.close()
