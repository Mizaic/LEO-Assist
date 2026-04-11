"""Full health check of ALL SurfaceForm nodes in the knowledge graph.

Checks:
  1. Total count and breakdown by provenance / status
  2. Wrong semantic tag mappings (qualifier value, finding, body structure, etc.)
  3. Multi-mapped forms (one form -> multiple concepts)
  4. Low-confidence edges (conf < 0.7)
  5. Forms where concept is inactive
  6. Sample of each problem category for review
"""

from __future__ import annotations

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
    sep = "=" * 65

    with driver.session() as s:

        # ---- 1. Total counts ----------------------------------------
        total = s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "RETURN count(DISTINCT sf) AS n"
        ).single()["n"]
        print(f"\n{sep}")
        print(f"TOTAL SurfaceForm nodes with MAPS_TO edge: {total}")
        print(sep)

        # ---- 2. By provenance ----------------------------------------
        print("\nBy provenance:")
        for row in s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "RETURN coalesce(r.provenance, 'none') AS prov, count(sf) AS n "
            "ORDER BY n DESC LIMIT 25"
        ):
            print(f"  {row['prov']:<45s} {row['n']}")

        # ---- 3. By status --------------------------------------------
        print("\nBy status:")
        for row in s.run(
            "MATCH (sf:SurfaceForm) "
            "RETURN coalesce(sf.status, 'none') AS status, count(sf) AS n "
            "ORDER BY n DESC"
        ):
            print(f"  {row['status']:<20s} {row['n']}")

        # ---- 4. Wrong semantic tag -----------------------------------
        bad_tags = [
            "qualifier value",
            "body structure",
            "organism",
            "substance",
            "attribute",
            "environment",
            "physical object",
            "regime/therapy",
        ]
        # finding and observable entity are OK for criteria context but
        # bad for action context; we flag them separately
        print("\nSurfaceForm -> wrong/non-clinical semantic tags:")
        for row in s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "WHERE c.semantic_tag IN $tags "
            "RETURN c.semantic_tag AS tag, count(sf) AS n "
            "ORDER BY n DESC",
            tags=bad_tags,
        ):
            print(f"  {row['tag']:<35s} {row['n']}")

        # Sample of bad-tag forms (up to 10)
        bad_samples = list(
            s.run(
                "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
                "WHERE c.semantic_tag IN $tags "
                "RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn, "
                "       c.semantic_tag AS tag, sf.status AS status "
                "ORDER BY sf.form LIMIT 10",
                tags=bad_tags,
            )
        )
        if bad_samples:
            print("  Samples:")
            for r in bad_samples:
                print(f"    {r['form']!r:<45s} -> {r['cid']} ({r['tag']})")
                print(f"    {'':45s}    {(r['fsn'] or '')[:55]}")

        # ---- 5. Multi-mapped (one form -> multiple concepts) ----------
        multi_count = s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "WITH sf, count(c) AS nc WHERE nc > 1 "
            "RETURN count(sf) AS n"
        ).single()["n"]
        print(f"\nMulti-mapped SurfaceForm nodes (-> >1 concept): {multi_count}")

        # Sample multi-mapped
        multi_samples = list(
            s.run(
                "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
                "WITH sf, count(c) AS nc WHERE nc > 1 "
                "MATCH (sf)-[r2:MAPS_TO]->(c2:Concept) "
                "RETURN sf.form AS form, c2.id AS cid, c2.fsn AS fsn, "
                "       r2.confidence AS conf, nc "
                "ORDER BY sf.form, r2.confidence DESC LIMIT 20"
            )
        )
        if multi_samples:
            current = None
            for r in multi_samples:
                if r["form"] != current:
                    print(f"  {r['form']!r} (maps to {r['nc']} concepts):")
                    current = r["form"]
                print(f"    conf={r['conf']} -> {r['cid']} | {(r['fsn'] or '')[:55]}")

        # ---- 6. Low confidence (<0.7) --------------------------------
        low_conf = s.run(
            "MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept) "
            "WHERE r.confidence < 0.7 "
            "RETURN count(sf) AS n"
        ).single()["n"]
        print(f"\nLow-confidence edges (conf < 0.7): {low_conf}")

        # ---- 7. Inactive concept mappings ----------------------------
        inactive = s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "WHERE c.active = false "
            "RETURN count(sf) AS n"
        ).single()["n"]
        print(f"Edges to inactive concepts: {inactive}")

        if inactive:
            print("  Samples:")
            for r in s.run(
                "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
                "WHERE c.active = false "
                "RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn "
                "LIMIT 10"
            ):
                print(f"    {r['form']!r:<45s} -> {r['cid']}")
                print(f"    {'':45s}    {(r['fsn'] or '')[:55]}")

        # ---- 8. SurfaceForm with no edges at all ---------------------
        orphan_nodes = s.run(
            "MATCH (sf:SurfaceForm) "
            "WHERE NOT (sf)-[:MAPS_TO]->() "
            "RETURN count(sf) AS n"
        ).single()["n"]
        print(f"Orphan SurfaceForm nodes (no MAPS_TO edge): {orphan_nodes}")

        # ---- 9. Finding/observable split for action context ----------
        obs_count = s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "WHERE c.semantic_tag IN ['observable entity', 'finding'] "
            "RETURN c.semantic_tag AS tag, count(sf) AS n ORDER BY n DESC"
        )
        print("\nSurfaceForm -> observable entity or finding (may be OK for criteria):")
        for row in obs_count:
            print(f"  {row['tag']:<35s} {row['n']}")

        # Sample observable/finding forms - show top 15 most notable
        print("  Sample observable/finding mappings (ordered by form):")
        for r in s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept) "
            "WHERE c.semantic_tag IN ['observable entity', 'finding'] "
            "RETURN sf.form AS form, c.id AS cid, c.fsn AS fsn, "
            "       c.semantic_tag AS tag "
            "ORDER BY sf.form LIMIT 20"
        ):
            print(
                f"    {r['form']!r:<45s} -> {r['tag'][:10]} "
                f"{r['cid']} | {(r['fsn'] or '')[:45]}"
            )

    driver.close()


if __name__ == "__main__":
    run()
