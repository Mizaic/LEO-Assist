"""Fix calprotectin mapped to 'Fecal occult blood requested (situation)'.

Calprotectin is a stool inflammatory marker used for IBD monitoring.
It is NOT related to fecal occult blood / FIT.
"""

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

_UPSERT = """
MATCH (c:Concept {id: $concept_id}) WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0, m.provenance = 'audit-fix-calprotectin-2026-04'
RETURN sf.normalized AS n, c.id AS id, c.fsn AS fsn
"""


def _norm(t):
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    # Find the correct calprotectin concept
    print("Searching for calprotectin concept:")
    rows = s.run("""
        CALL db.index.fulltext.queryNodes('term_fulltext', 'calprotectin') YIELD node, score
        MATCH (node)-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true
        RETURN c.id AS id, c.fsn AS fsn, c.semantic_tag AS tag, score
        ORDER BY score DESC LIMIT 5
    """).data()
    for r in rows:
        print(f"  {r['id']} | {r['fsn']} [{r['tag']}] score={r['score']:.2f}")

    if rows:
        best = rows[0]
        cid = best["id"]

        # Forms to fix
        forms = [
            "calproctectin",
            "calprotectin",
            "faecal calprotectin",
            "fecal calprotectin",
            "stool calprotectin",
        ]

        print(f"\nUpserting -> {cid} | {best['fsn']}")
        for form in forms:
            norm = _norm(form)
            # Delete wrong edge to fecal occult blood (167666002)
            s.run(
                """
                MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: '167666002'})
                DELETE m
            """,
                normalized=norm,
            )
            r = s.run(_UPSERT, normalized=norm, form=form, concept_id=cid).data()
            if r:
                print(f"  OK {form!r} -> {cid}")
            else:
                print(f"  FAIL {form!r} (concept not in graph?)")

driver.close()
