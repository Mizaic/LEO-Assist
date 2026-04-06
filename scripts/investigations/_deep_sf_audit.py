"""Deep audit of ALL surface form quality issues across the knowledge graph.

Outputs a prioritised fix plan covering:
  P0 - Clearly wrong concept type (body structure, qualifier value, organism)
  P1 - Multi-mapped forms with equal confidence (ambiguous resolver output)
  P2 - regime/therapy and substance forms (may be intentional; flag for review)
  P3 - 307 orphan SurfaceForm nodes with no MAPS_TO edge (cleanup)
  P4 - Low-confidence edges < 0.7
"""
from __future__ import annotations

import json
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

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")


def run() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    with driver.session() as s:

        # ------------------------------------------------------------------ #
        # P0 - Wrong concept type: body structure / qualifier value / organism #
        # ------------------------------------------------------------------ #
        p0_tags = ["body structure", "qualifier value", "organism", "attribute",
                   "environment", "physical object"]
        p0 = list(s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "WHERE c.semantic_tag IN $tags "
            "RETURN sf.normalized AS normalized, sf.form AS form, "
            "       c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag, "
            "       r.confidence AS conf, r.provenance AS prov "
            "ORDER BY sf.form",
            tags=p0_tags,
        ))
        print(f"\n{'='*65}")
        print(f"P0 - WRONG CONCEPT TYPE ({len(p0)} forms)")
        print(f"{'='*65}")
        for r in p0:
            print(f"  {r['form']!r:<50s} -> {r['tag']}")
            print(f"  {'':50s}    {r['cid']} | {(r['fsn'] or '')[:50]}")

        # ------------------------------------------------------------------ #
        # P1 - Multi-mapped at equal confidence                               #
        # ------------------------------------------------------------------ #
        print(f"\n{'='*65}")
        print("P1 - MULTI-MAPPED FORMS (both concepts at same confidence)")
        print(f"{'='*65}")
        p1 = list(s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "WITH sf, count(c) AS nc, max(r.confidence) AS mc, "
            "     min(r.confidence) AS lc "
            "WHERE nc > 1 AND mc = lc "
            "RETURN sf.normalized AS normalized, sf.form AS form, nc, mc "
            "ORDER BY sf.form"
        ))
        for row in p1:
            print(f"\n  {row['form']!r} (x{row['nc']}, all conf={row['mc']}):")
            for edge in s.run(
                "MATCH (sf:SurfaceForm {normalized: $n})-[r:MAPS_TO]->(c:Concept) "
                "RETURN c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag "
                "ORDER BY c.id",
                n=row["normalized"],
            ):
                print(f"    {edge['cid']} | {(edge['fsn'] or '')[:55]} ({edge['tag']})")

        # ------------------------------------------------------------------ #
        # P2 - regime/therapy and substance                                    #
        # ------------------------------------------------------------------ #
        p2_tags = ["regime/therapy", "substance"]
        p2 = list(s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "WHERE c.semantic_tag IN $tags "
            "RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn, "
            "       c.semantic_tag AS tag, r.confidence AS conf, r.provenance AS prov "
            "ORDER BY c.semantic_tag, sf.form",
            tags=p2_tags,
        ))
        print(f"\n{'='*65}")
        print(f"P2 - REGIME/THERAPY AND SUBSTANCE ({len(p2)} forms)")
        print("(these may be intentional; verify each makes clinical sense)")
        print(f"{'='*65}")
        for r in p2:
            print(f"  [{r['tag'][:3]}] {r['form']!r:<50s} -> {r['cid']}")
            print(f"       {'':50s}    {(r['fsn'] or '')[:52]}")

        # ------------------------------------------------------------------ #
        # P3 - Orphan nodes                                                    #
        # ------------------------------------------------------------------ #
        orphan_count = s.run(
            "MATCH (sf:SurfaceForm) WHERE NOT (sf)-[:MAPS_TO]->() "
            "RETURN count(sf) AS n"
        ).single()["n"]
        print(f"\n{'='*65}")
        print(f"P3 - ORPHAN SURFACEFORM NODES (no MAPS_TO edge): {orphan_count}")
        print(f"{'='*65}")
        print("  Sample (first 15):")
        for r in s.run(
            "MATCH (sf:SurfaceForm) WHERE NOT (sf)-[:MAPS_TO]->() "
            "RETURN sf.normalized AS normalized, sf.form AS form, "
            "       sf.status AS status, sf.source AS source LIMIT 15"
        ):
            print(f"  {r['form']!r} [status={r['status']}] [source={r['source']}]")

        # ------------------------------------------------------------------ #
        # P4 - Low confidence                                                  #
        # ------------------------------------------------------------------ #
        p4 = list(s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "WHERE r.confidence < 0.7 "
            "RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn, "
            "       r.confidence AS conf, r.provenance AS prov "
            "ORDER BY r.confidence"
        ))
        print(f"\n{'='*65}")
        print(f"P4 - LOW CONFIDENCE EDGES (<0.7): {len(p4)}")
        print(f"{'='*65}")
        for r in p4:
            print(f"  {r['form']!r:<50s} conf={r['conf']}")
            print(f"  -> {r['cid']} | {(r['fsn'] or '')[:55]}")

    driver.close()
    print("\nAudit complete.")


if __name__ == "__main__":
    run()
