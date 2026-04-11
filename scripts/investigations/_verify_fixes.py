"""Verify the state of GCL surface form fixes."""

import os
import sys
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

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    # Find correct emphysema concept
    print("Emphysema concepts in graph:")
    rows = s.run("""
        CALL db.index.fulltext.queryNodes('term_fulltext', 'emphysema') YIELD node, score
        MATCH (node)-[:DESCRIBES]->(c:Concept)
        WHERE c.active = true AND c.semantic_tag = 'disorder'
        RETURN c.id AS id, c.fsn AS fsn, score ORDER BY score DESC LIMIT 8
    """).data()
    for r in rows:
        print(f"  {r['id']} | {r['fsn']} score={r['score']:.3f}")

    # Total remaining GCL edges
    r = s.run(
        "MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept) WHERE m.provenance = 'guideline_config_loader' RETURN count(m) AS n"
    ).data()
    print(f"\nTotal remaining GCL edges: {r[0]['n']}")

    # Remaining wrong situation edges (the specific catch-all situation IDs)
    wrong_sit_ids = [
        "415036007",
        "275552000",
        "308064009",
        "270473001",
        "472961001",
        "161535005",
        "161465002",
        "267004000",
    ]
    r2 = s.run(
        """
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.provenance = 'guideline_config_loader'
          AND c.id IN $ids
        RETURN count(m) AS n, collect(sf.form)[..10] AS sample
    """,
        ids=wrong_sit_ids,
    ).data()
    print(f"GCL edges to known wrong situation concepts: {r2[0]['n']}")
    if r2[0]["n"] > 0:
        print(f"  sample: {r2[0]['sample']}")

    # Check specific spot-checks
    checks = [
        ("copd", "Should be COPD disorder"),
        ("stroke", "Should be CVA disorder"),
        ("rheumatoid arthritis", "Should be RA disorder"),
        ("hemiplegia", "Should be hemiplegia disorder"),
        ("paraplegia", "Should be paraplegia disorder"),
        ("diabetes mellitus type 2", "Should be T2DM"),
        ("alzheimer's", "Should be Alzheimer's disease"),
        ("emphysema", "Should be emphysema disorder"),
    ]
    print("\nSpot checks (current best mapping):")
    for norm, label in checks:
        r3 = s.run(
            """
            MATCH (sf:SurfaceForm {normalized: $norm})-[m:MAPS_TO]->(c:Concept)
            WHERE c.active = true
            RETURN c.id AS id, c.fsn AS fsn, m.confidence AS conf, m.provenance AS prov
            ORDER BY m.confidence DESC LIMIT 2
        """,
            norm=norm,
        ).data()
        if r3:
            best = r3[0]
            print(
                f"  {norm!r}: {best['id']} | {best['fsn']} (conf={best['conf']}) -- {label}"
            )
        else:
            print(f"  {norm!r}: NO MAPPING (falls to fulltext) -- {label}")

driver.close()
