"""Pin mesothelioma fast-track referral surface forms to the lung cancer
2WW pathway concept (276491000000101).

UK SNOMED CT has no separate code for a mesothelioma suspected cancer
pathway referral.  NICE NG12 directs mesothelioma referrals via the lung
cancer pathway, so the lung cancer fast-track concept is the correct code.
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

from libs.terminology.surface_normalize import normalize_surface
from neo4j import GraphDatabase

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.created_at = datetime(), r.approved_at = datetime()
SET r.confidence = $conf, r.provenance = $prov
RETURN sf.form AS form, c.id AS cid, r.confidence AS conf
"""

FORMS = [
    ("fast track referral for suspected mesothelioma", "276491000000101", 1.0),
    ("suspected mesothelioma referral", "276491000000101", 0.97),
    ("mesothelioma referral", "276491000000101", 0.95),
    ("urgent referral for suspected mesothelioma", "276491000000101", 0.95),
]


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for form, cid, conf in FORMS:
            rows = list(
                s.run(
                    _UPSERT,
                    normalized=normalize_surface(form),
                    form=form,
                    cid=cid,
                    conf=conf,
                    prov="manual-fix-mesothelioma",
                )
            )
            if rows:
                r = rows[0]
                print(f"  OK  {r['form']!r} -> {r['cid']} (conf={r['conf']})")
            else:
                print(f"  MISS  {form!r} -> concept {cid} not found in graph")
    driver.close()


if __name__ == "__main__":
    main()
