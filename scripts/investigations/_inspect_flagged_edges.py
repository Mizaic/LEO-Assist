"""Inspect the 9 flagged DELETE edges before applying."""

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

FORMS_TO_CHECK = [
    "faecal immunochemical test positive",
    "FIT positive",
    "FIT",
    "HbA1c",
    "bone metastases",
    "CMHT",
    "CRHTT",
    "Lewy body dementia",
    "urine albumin creatinine ratio",
]

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
import re


def _norm(t):
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


with driver.session() as s:
    for form in FORMS_TO_CHECK:
        normalized = _norm(form)
        rows = s.run(
            """
            MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
            RETURN c.id AS id, c.fsn AS fsn, c.semantic_tag AS tag,
                   c.active AS active, m.confidence AS conf, m.provenance AS prov
            ORDER BY m.confidence DESC, m.provenance
        """,
            normalized=normalized,
        ).data()
        print(f"\n{form!r} (norm={normalized!r}):")
        if not rows:
            print("  (no surface form mappings)")
        for r in rows:
            active = "ACTIVE" if r["active"] else "INACTIVE"
            print(f"  [{active}] {r['id']} | {r['fsn']}")
            print(f"    tag={r['tag']}  conf={r['conf']}  prov={r['prov']}")

driver.close()
