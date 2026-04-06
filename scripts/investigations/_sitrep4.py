"""Assertion breakdown across old and new DOCUMENTS edge styles."""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv("secrets/.env.config", override=False)
load_dotenv("secrets/.env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from neo4j import GraphDatabase

pg_uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "bolt://localhost:7687")
pg_user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "") or os.getenv("NEO4J_PATIENT_PASSWORD", "patient-dev")
d = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))

cypher = """
MATCH ()-[r:DOCUMENTS]->()
RETURN coalesce(r.assertion, r.context, 'unknown') AS a, count(r) AS n
ORDER BY n DESC
"""

with d.session() as s:
    for row in s.run(cypher):
        label = str(row["a"])[:60]
        print(f"  {label:<30} {row['n']:>8,}")

d.close()
