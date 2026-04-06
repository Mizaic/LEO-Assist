"""Check what FIT surface forms already exist in the knowledge graph."""
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from neo4j import GraphDatabase

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI",     "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    rows = s.run("""
        MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
        WHERE toLower(sf.form) CONTAINS 'fit'
           OR toLower(sf.form) CONTAINS 'faecal'
           OR toLower(sf.form) CONTAINS 'fecal'
           OR toLower(sf.form) CONTAINS 'immunochemical'
           OR toLower(sf.form) CONTAINS 'occult'
        RETURN sf.form AS form, sf.normalized AS norm,
               c.id AS concept_id, r.confidence AS conf, r.source AS src
        ORDER BY sf.form
    """).data()

print(f"Found {len(rows)} FIT-related surface forms:\n")
for row in rows:
    print(f"  [{row['conf']:.1f}] {row['form']!r:40s} -> {row['concept_id']}  [{row['src']}]")

driver.close()
