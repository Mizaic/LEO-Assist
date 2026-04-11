"""Check what surface forms exist for the 3 previously-pinned concept IDs."""

import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

CONCEPT_IDS = ["1290960005", "272016000", "405749004"]

QUERY = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:SNOMEDConcept {concept_id: $cid})
RETURN c.concept_id AS cid, c.preferred_term AS pt,
       sf.normalized AS sf,
       coalesce(m.pinned, false) AS pinned,
       coalesce(m.confidence, 0) AS conf
ORDER BY pinned DESC, conf DESC
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    for cid in CONCEPT_IDS:
        rows = list(s.run(QUERY, cid=cid))
        print(f"\n=== {cid} ({rows[0]['pt'] if rows else 'NOT IN GRAPH'}) ===")
        if not rows:
            print("  No SNOMEDConcept node found - concept not in graph at all")
        for row in rows:
            flag = "PINNED" if row["pinned"] else "auto  "
            print(f"  [{flag}] {row['sf']!r:60s} conf={row['conf']:.2f}")
driver.close()
