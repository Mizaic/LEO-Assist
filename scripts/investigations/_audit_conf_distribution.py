"""Audit confidence distribution across all surface form provenances."""

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
driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    # Confidence distribution by provenance
    r = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        RETURN m.provenance AS prov,
               count(m) AS total,
               sum(CASE WHEN m.confidence >= 1.0 THEN 1 ELSE 0 END) AS conf_1,
               sum(CASE WHEN m.confidence >= 0.9 AND m.confidence < 1.0 THEN 1 ELSE 0 END) AS conf_09,
               sum(CASE WHEN m.confidence < 0.9 THEN 1 ELSE 0 END) AS conf_low,
               round(min(m.confidence), 3) AS min_conf,
               round(max(m.confidence), 3) AS max_conf
        ORDER BY total DESC
    """).data()
    print(
        f"{'PROVENANCE':<50} {'TOTAL':>7} {'conf=1':>7} {'0.9-1':>7} {'<0.9':>7} {'MIN':>7} {'MAX':>7}"
    )
    print("-" * 100)
    for row in r:
        print(
            f"{str(row['prov']):<50} {row['total']:>7} {row['conf_1']:>7} {row['conf_09']:>7} {row['conf_low']:>7} {str(row['min_conf']):>7} {str(row['max_conf']):>7}"
        )

    # Total counts
    total = s.run(
        "MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept) RETURN count(m) AS n"
    ).data()
    print(f"\nTotal MAPS_TO edges: {total[0]['n']}")

    # Sample of low confidence forms by any provenance
    low = s.run("""
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE m.confidence < 0.9
        RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn,
               m.confidence AS conf, m.provenance AS prov
        ORDER BY m.confidence ASC LIMIT 20
    """).data()
    print(f"\nLow confidence forms (conf<0.9): {len(low)} shown")
    for row in low:
        print(
            f"  {row['form']!r} -> {row['cid']} | {row['fsn']} conf={row['conf']} [{row['prov']}]"
        )

driver.close()
