"""Verify final FIT surface form mappings in the knowledge graph."""

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

driver = GraphDatabase.driver(
    os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688"),
    auth=(
        os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j"),
        os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev"),
    ),
)

CHECK_FORMS = [
    "FIT Neg",
    "FIT neg",
    "FIT negative",
    "FIT pos",
    "FIT positive",
    "POSITIVE FIT",
    "FIT posotive",
    "negative FIT test",
    "FIT -",
    "FIT +",
    "FIT >10",
    "FIT>10",
    "FIT <10",
    "FIT<10",
]

EXPECTED = {
    "fit neg": "167667006",
    "fit negative": "167667006",
    "fit -": "167667006",
    "fit <10": "167667006",
    "fit<10": "167667006",
    "negative fit test": "167667006",
    "fit pos": "71711000112103",
    "fit positive": "71711000112103",  # has 2 mappings; highest conf wins
    "positive fit": "71711000112103",
    "fit posotive": "71711000112103",
    "fit +": "71711000112103",
    "fit >10": "71711000112103",
    "fit>10": "71711000112103",
}

with driver.session() as s:
    rows = s.run(
        """
        MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
        WHERE sf.form IN $forms
        RETURN sf.form AS form, c.id AS cid, r.confidence AS conf
        ORDER BY sf.form, r.confidence DESC
        """,
        forms=CHECK_FORMS,
    ).data()

print(f"\n{'Form':35s}  {'Concept ID':22s}  Conf  Status")
print("-" * 75)

seen: set[str] = set()
for r in rows:
    form = r["form"]
    cid = r["cid"]
    conf = r["conf"]
    norm = form.lower().strip()

    # Only check first (highest-conf) row per form
    if norm in seen:
        tag = "(dup)"
    else:
        seen.add(norm)
        expected = EXPECTED.get(norm)
        if expected is None:
            tag = "UNCHECKED"
        elif cid == expected:
            tag = "OK"
        else:
            tag = f"WRONG (expected {expected})"

    print(f"  {form:33s}  {cid:22s}  {conf:.1f}   {tag}")

driver.close()
