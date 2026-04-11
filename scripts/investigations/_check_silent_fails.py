"""Check verbatim text for silent CH002 failures."""

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

targets = [
    "NG12:v1:CH002:SEC002:R003",
    "NG12:v1:CH002:SEC004:R003",
    "NG12:v1:CH002:SEC006:R006",
]
QUERY = """
MATCH (r:Recommendation {id: $rid})
RETURN r.id AS id, r.title AS title, r.verbatim AS verbatim
"""
driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    for t in targets:
        row = s.run(QUERY, rid=t).single()
        if row:
            print(f"=== {row['id']} ({row['title']}) ===")
            print(row["verbatim"] or "(empty)")
            print()
driver.close()
