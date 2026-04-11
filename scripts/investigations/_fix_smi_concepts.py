"""Fix wrong SMI mapping and find correct concept IDs for failed upserts."""

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

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

SEARCHES = [
    ("severe mental illness", "disorder"),
    ("severe mental disorder", "disorder"),
    ("community mental health team", "finding"),
    ("thrombocytosis", "finding"),
    ("weight loss", "finding"),
]

with driver.session() as s:
    # First: show what 75478009 actually is
    r = s.run("MATCH (c:Concept {id: '75478009'}) RETURN c.id, c.fsn, c.active").data()
    print(f"75478009: {r}")

    # Delete the wrong SMI edge
    r2 = s.run("""
        MATCH (sf:SurfaceForm {normalized: 'smi'})-[m:MAPS_TO]->(c:Concept {id: '75478009'})
        DELETE m RETURN count(m) AS deleted
    """).data()
    print(f"Deleted wrong SMI edge: {r2}")

    for term, tag in SEARCHES:
        print(f"\nSearch: {term!r} (tag={tag})")
        rows = s.run(
            """
            CALL db.index.fulltext.queryNodes('term_fulltext', $q) YIELD node, score
            MATCH (node)-[:DESCRIBES]->(c:Concept)
            WHERE c.active = true AND c.semantic_tag = $tag
            RETURN c.id AS id, c.fsn AS fsn, score
            ORDER BY score DESC LIMIT 5
        """,
            q=term,
            tag=tag,
        ).data()
        for r in rows:
            print(f"  {r['id']} | {r['fsn']} score={r['score']:.2f}")

driver.close()
