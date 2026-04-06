"""Check pinned surface forms are present and correctly wired in Neo4j.

Verifies that MAPS_TO edges exist with pinned=true for the target concept IDs.
"""
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

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

CHECKS = [
    ("1290960005", "Mesothelioma CXR finding",
     ["chest X-ray findings suggestive of mesothelioma",
      "pleural thickening on chest X-ray",
      "CXR findings suggestive of mesothelioma"]),
    ("272016000",  "On examination - chest finding (pleural signs)",
     ["chest signs compatible with pleural disease",
      "chest signs consistent with pleural disease",
      "on examination chest finding"]),
    ("405749004",  "Newly diagnosed diabetes",
     ["new-onset diabetes mellitus", "newly diagnosed diabetes mellitus",
      "new onset diabetes"]),
    ("389026000",  "Ascites (disorder)",      ["ascites", "abdominal ascites"]),
    ("271683004",  "Gallbladder palpable",     ["palpable gallbladder", "gallbladder palpable"]),
    ("300344005",  "Gallbladder enlarged",     ["enlarged gallbladder"]),
    ("300482003",  "Finding of appearance of testes",
     ["change in shape of testis", "change in texture of testis"]),
    ("13028004",   "Abnormal nervous system function",
     ["progressive neurological deficit", "sub-acute neurological deterioration"]),
    ("30425001",   "Osteolysis",
     ["osteolysis", "X-ray finding suggestive of bone sarcoma"]),
    ("1812681000000102", "Mass of anal structure",
     ["anal mass", "mass of anal structure"]),
    ("248523006",  "Rectal mass",             ["rectal mass"]),
]

QUERY = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $cid})
RETURN sf.normalized AS sf, c.id AS cid, c.fsn AS pt,
       coalesce(m.pinned, false) AS pinned, coalesce(m.confidence, 0) AS conf
"""

from libs.terminology.surface_normalize import normalize_surface

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
all_ok = True
with driver.session() as s:
    for cid, label, surface_forms in CHECKS:
        print(f"\n--- {cid} | {label} ---")
        found_any = False
        for sf in surface_forms:
            row = s.run(QUERY, normalized=normalize_surface(sf), cid=cid).single()
            if row:
                flag = "OK " if row["pinned"] else "WARN (not pinned)"
                print(f"  [{flag}] {sf!r} -> {row['cid']} conf={row['conf']}")
                found_any = True
            else:
                print(f"  [MISS] {sf!r} -> NOT FOUND in graph")
                all_ok = False
        if not found_any:
            all_ok = False
driver.close()
print("\n" + ("ALL OK" if all_ok else "SOME MISSING - review above"))
