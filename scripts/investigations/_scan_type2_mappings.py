"""Find every SurfaceForm that might resolve 'type 2 diabetes' to 410657003."""

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
driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))


def run(q, **p):
    with driver.session() as s:
        return list(s.run(q, **p))


# 1. Find anything pointing to 410657003
print("=== All SurfaceForm MAPS_TO 410657003 ===")
rows = run(
    """
    MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: '410657003'})
    RETURN sf.normalized AS norm, sf.form AS form,
           m.confidence AS conf, m.provenance AS prov
    ORDER BY m.confidence DESC
    """,
)
print(f"  Found {len(rows)} mapping(s) to 410657003:")
for r in rows:
    print(
        f"    norm='{r['norm']}'  form='{r['form']}'  conf={r['conf']}  prov={r['prov']}"
    )

# 2. Find all normalized forms that contain 'type 2' or 'diabetes'
print("\n=== All SurfaceForm nodes matching 'type 2' or 'diabetes' ===")
rows = run(
    """
    MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
    WHERE sf.normalized CONTAINS 'diabetes' OR sf.normalized CONTAINS 'type 2'
    RETURN sf.normalized AS norm, c.id AS concept_id, m.confidence AS conf,
           m.provenance AS prov
    ORDER BY sf.normalized, m.confidence DESC
    """,
)
prev_norm = None
for r in rows:
    if r["norm"] != prev_norm:
        print(f"\n  '{r['norm']}':")
        prev_norm = r["norm"]
    print(f"    [{r['concept_id']}] conf={r['conf']}  prov={r['prov']}")

driver.close()
