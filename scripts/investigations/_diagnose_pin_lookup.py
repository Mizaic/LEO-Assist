"""Diagnose why pinned concepts aren't being returned by the resolver.

Checks:
  1. Is the Concept node active?
  2. Does the SurfaceForm -> Concept edge exist?
  3. What does a direct /resolve API call return for our pinned terms?
"""

import asyncio, os, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import httpx
from libs.terminology.surface_normalize import normalize_surface
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

TERM_API = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8002")

CHECKS = [
    {
        "label": "Mesothelioma CXR (1.1.4)",
        "concept_id": "9990010014",
        "resolve_terms": [
            "chest X-ray findings suggestive of mesothelioma",
            "pleural thickening on chest X-ray",
            "CXR mesothelioma",
        ],
    },
    {
        "label": "New-onset diabetes (1.2.5)",
        "concept_id": "405749004",
        "resolve_terms": [
            "new-onset diabetes mellitus",
            "new onset diabetes mellitus",
            "newly diagnosed diabetes mellitus",
        ],
    },
]

NEO4J_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})
OPTIONAL MATCH (sf)-[m:MAPS_TO]->(c:Concept)
RETURN sf.normalized AS sf, sf.status AS sf_status,
       c.id AS cid, c.fsn AS fsn, c.active AS active,
       coalesce(m.confidence, -1) AS conf, coalesce(m.pinned, false) AS pinned
"""

CONCEPT_CHECK = """
MATCH (c:Concept {id: $cid})
RETURN c.id AS cid, c.fsn AS fsn, c.active AS active, c.semantic_tag AS tag
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

for check in CHECKS:
    print(f"\n{'='*60}")
    print(f"=== {check['label']} - target {check['concept_id']} ===")
    print(f"{'='*60}")

    # 1. Check concept node
    with driver.session() as s:
        row = s.run(CONCEPT_CHECK, cid=check["concept_id"]).single()
    if row:
        print(
            f"  Concept node: id={row['cid']} active={row['active']} tag={row['tag']}"
        )
        print(f"    fsn: {row['fsn']}")
    else:
        print(f"  Concept node: NOT FOUND in graph")

    # 2. Check surface form edges
    print()
    with driver.session() as s:
        for term in check["resolve_terms"]:
            norm = normalize_surface(term)
            rows = list(s.run(NEO4J_CHECK, normalized=norm))
            if rows:
                for row in rows:
                    hit = "TARGET" if row["cid"] == check["concept_id"] else "OTHER"
                    print(f"  SF [{hit}] {norm!r}")
                    print(
                        f"         -> {row['cid']} active={row['active']} "
                        f"conf={row['conf']} pinned={row['pinned']}"
                    )
            else:
                print(f"  SF [MISS] {norm!r} -> no SurfaceForm node found")

    # 3. Live /resolve call
    print()
    for term in check["resolve_terms"]:
        try:
            resp = httpx.post(
                f"{TERM_API}/terminology/resolve",
                json={"terms": [term], "k": 10},
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", {}).get(term, [])
                ids = [r.get("concept_id") for r in results]
                found_target = check["concept_id"] in ids
                flag = "FOUND" if found_target else "MISS "
                print(f"  API [{flag}] resolve({term!r})")
                for r in results[:5]:
                    marker = (
                        " <-- TARGET"
                        if r.get("concept_id") == check["concept_id"]
                        else ""
                    )
                    print(
                        f"         {r.get('concept_id')} | {r.get('fsn','?')[:60]} "
                        f"score={r.get('score',0):.3f}{marker}"
                    )
            else:
                print(f"  API [ERR ] {resp.status_code} for {term!r}")
        except Exception as e:
            print(f"  API [EXC ] {term!r}: {e}")

driver.close()
print("\nDone.")
