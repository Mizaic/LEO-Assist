"""Check CH003 recommendation content in Neo4j to diagnose silent failures."""
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

QUERY = """
MATCH (g:Guideline {id: 'NG12'})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE r.id STARTS WITH 'NG12:v1:CH003'
RETURN r.id AS id, r.title AS title, r.isNormative AS normative,
       r.urgency AS urgency,
       left(coalesce(r.verbatim, ''), 200) AS verbatim_preview
ORDER BY r.id
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    rows = list(s.run(QUERY))
driver.close()

print(f"Found {len(rows)} CH003 recommendations\n")
for row in rows:
    print(f"ID:       {row['id']}")
    print(f"Title:    {row['title']}")
    print(f"Normative:{row['normative']}")
    print(f"Urgency:  {row['urgency']}")
    verbatim = row['verbatim_preview'] or ''
    print(f"Verbatim: {repr(verbatim[:120])}")
    print()
