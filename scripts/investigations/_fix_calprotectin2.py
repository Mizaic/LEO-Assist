"""Switch calprotectin to observable entity concept."""

import os, sys, re
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

CORRECT_CID = "1031581000000104"  # Calprotectin level (observable entity)
WRONG_CID = "442069007"  # Calprotectin (substance)

FORMS = [
    "calproctectin",
    "calprotectin",
    "faecal calprotectin",
    "fecal calprotectin",
    "stool calprotectin",
]


def _norm(t):
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


_DEL = "MATCH (sf:SurfaceForm {normalized: $n})-[m:MAPS_TO]->(c:Concept {id: $cid}) DELETE m"
_UPSERT = """
MATCH (c:Concept {id: $cid}) WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $n})
ON CREATE SET sf.form = $f, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0, m.provenance = 'audit-fix-calprotectin-2026-04'
RETURN c.fsn AS fsn
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    for form in FORMS:
        n = _norm(form)
        s.run(_DEL, n=n, cid=WRONG_CID)
        r = s.run(_UPSERT, n=n, f=form, cid=CORRECT_CID).data()
        fsn = r[0]["fsn"] if r else "FAIL"
        print(f"  {form!r} -> {CORRECT_CID} | {fsn}")
driver.close()
