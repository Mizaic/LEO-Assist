"""Check DOCUMENTS edge structure and assertion breakdown."""

import os
import sys
import warnings
import json

warnings.filterwarnings("ignore")
ROOT_DIR = __file__
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv("secrets/.env.config", override=False)
load_dotenv("secrets/.env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

pg_uri = os.getenv("NEO4J_URI", "") or os.getenv(
    "NEO4J_PATIENT_URI", "bolt://localhost:7687"
)
pg_user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "") or os.getenv(
    "NEO4J_PATIENT_PASSWORD", "patient-dev"
)
d = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))

with d.session() as s:
    # Property inventory
    ctx = s.run(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.context IS NOT NULL RETURN count(r) AS n"
    ).single()["n"]
    ass = s.run(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.assertion IS NOT NULL RETURN count(r) AS n"
    ).single()["n"]
    rem = s.run(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.remediated_at IS NOT NULL RETURN count(r) AS n"
    ).single()["n"]
    no_coding = s.run(
        "MATCH (e:Encounter) WHERE NOT (e)-[:DOCUMENTS]->() RETURN count(e) AS n"
    ).single()["n"]

    print(f"Edges with context property:  {ctx:,}")
    print(f"Edges with assertion property: {ass:,}")
    print(f"Edges remediated_at set:       {rem:,}")
    print(f"Encounters with NO coding:     {no_coding:,}")

    print()
    print("Assertion property breakdown:")
    for row in s.run(
        "MATCH ()-[r:DOCUMENTS]->() RETURN r.assertion AS a, count(r) AS n ORDER BY n DESC"
    ):
        label = row["a"]
        print(f"  {label:<20} {row['n']:>8,}")

    # Sample a remediated edge
    rows = s.run(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.remediated_at IS NOT NULL RETURN r LIMIT 1"
    )
    for row in rows:
        props = dict(row["r"])
        print()
        print("Sample remediated DOCUMENTS edge props:", sorted(props.keys()))

d.close()
