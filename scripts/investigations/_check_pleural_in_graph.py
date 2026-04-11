"""Find pleural-related concepts that actually exist in Neo4j."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session() as s:
    rows = list(s.run("""
        MATCH (c:Concept)
        WHERE toLower(c.fsn) CONTAINS 'pleural'
        RETURN c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag
        ORDER BY c.fsn
        LIMIT 30
        """))
driver.close()

print(f"Found {len(rows)} pleural concepts in graph:\n")
for row in rows:
    print(f"  {row['cid']:20s} ({row['tag']:30s}) {row['fsn']}")
