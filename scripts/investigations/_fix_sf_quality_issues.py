"""Fix all surface form quality issues identified by _deep_sf_audit.py.

Fixes applied:
  P0a  Atypical depression -> myocardium: delete edge, add correct disorder
  P0b  Separation anxiety -> Clevidipine: delete edge, add correct disorder
  P1a  Emphysema -> Toxic emphysema: remove wrong edge (keep pulmonary)
  P1b  Pulmonary emphysema -> Toxic emphysema: remove wrong edge
  P1c  Past COPD -> COPD disorder: remove wrong edge (keep history situation)
  P1d  high platelet count -> thrombocytosis: keep finding, remove disorder
  P4   stopped Diannette a year ago: delete (not a clinical concept)
  P3   307 orphan ncda_preapproved nodes: DETACH DELETE (cleanup only)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

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

PROV = "sf-quality-fix-2026-04-05"


def normalize_surface(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# -- Generic Cypher helpers ------------------------------------------

_DELETE_EDGE = """
MATCH (sf:SurfaceForm {normalized: $norm})-[r:MAPS_TO]->(c:Concept {id: $cid})
DELETE r
RETURN count(r) AS deleted
"""

_DELETE_NODE = """
MATCH (sf:SurfaceForm {normalized: $norm})
DETACH DELETE sf
RETURN count(sf) AS deleted
"""

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.created_at = datetime(), r.approved_at = datetime()
SET r.confidence = $conf, r.provenance = $prov
RETURN sf.normalized AS normalized, sf.form AS form,
       c.id AS cid, r.confidence AS conf
"""

_DETACH_ORPHANS = """
MATCH (sf:SurfaceForm)
WHERE NOT (sf)-[:MAPS_TO]->()
DETACH DELETE sf
RETURN count(sf) AS deleted
"""


def del_edge(s, form: str, wrong_cid: str) -> int:
    norm = normalize_surface(form)
    rows = list(s.run(_DELETE_EDGE, norm=norm, cid=wrong_cid))
    return rows[0]["deleted"] if rows else 0


def del_node(s, form: str) -> int:
    norm = normalize_surface(form)
    rows = list(s.run(_DELETE_NODE, norm=norm))
    return rows[0]["deleted"] if rows else 0


def upsert(s, form: str, cid: str, conf: float) -> bool:
    norm = normalize_surface(form)
    rows = list(s.run(_UPSERT, normalized=norm, form=form,
                       cid=cid, conf=conf, prov=PROV))
    return bool(rows)


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    print("Applying surface form quality fixes ...\n")

    with driver.session() as s:

        # ------------------------------------------------------------ #
        # P0a - Atypical depression -> myocardium (body structure)       #
        # Correct code: 426566006 | Atypical depression (disorder)       #
        # ------------------------------------------------------------ #
        print("P0a: Atypical depression -> myocardium (body structure)")
        d = del_edge(s, "Atypical depression", "192084000")
        print(f"     Deleted wrong edge: {d}")
        ok = upsert(s, "Atypical depression", "426566006", 1.0)
        ok2 = upsert(s, "atypical depression", "426566006", 1.0)
        print(f"     Upserted correct disorder (426566006): {'OK' if ok else 'MISS'}")

        # ------------------------------------------------------------ #
        # P0b - Separation anxiety -> Clevidipine (substance)            #
        # Correct code: 9855006 | Separation anxiety (disorder)          #
        # ------------------------------------------------------------ #
        print("\nP0b: Separation anxiety -> Clevidipine (substance)")
        d = del_edge(s, "Separation anxiety", "439471002")
        print(f"     Deleted wrong edge: {d}")
        ok = upsert(s, "Separation anxiety", "9855006", 1.0)
        ok2 = upsert(s, "separation anxiety", "9855006", 1.0)
        print(f"     Upserted correct disorder (9855006): {'OK' if ok else 'MISS'}")

        # ------------------------------------------------------------ #
        # P1a - Emphysema also maps to Toxic emphysema 233675009         #
        # Keep: 87433001 | Pulmonary emphysema (disorder)                #
        # ------------------------------------------------------------ #
        print("\nP1a: Emphysema - remove Toxic emphysema mapping")
        d = del_edge(s, "Emphysema", "233675009")
        print(f"     Deleted toxic emphysema edge: {d}")

        # ------------------------------------------------------------ #
        # P1b - Pulmonary emphysema also maps to Toxic emphysema         #
        # ------------------------------------------------------------ #
        print("\nP1b: Pulmonary emphysema - remove Toxic emphysema mapping")
        d = del_edge(s, "Pulmonary emphysema", "233675009")
        print(f"     Deleted toxic emphysema edge: {d}")

        # ------------------------------------------------------------ #
        # P1c - Past COPD maps to COPD disorder AND history situation    #
        # Keep: 270473001 | History of COPD (situation)                  #
        # Remove: 13645005 | COPD (disorder)                             #
        # ------------------------------------------------------------ #
        print("\nP1c: Past COPD - remove COPD disorder, keep history situation")
        d = del_edge(s, "Past COPD", "13645005")
        print(f"     Deleted COPD disorder edge: {d}")

        # ------------------------------------------------------------ #
        # P1d - high platelet count -> both finding and disorder         #
        # Keep: 415115007 | Platelet count above reference range (finding)#
        # Remove: 6631009 | Thrombocytosis (disorder)                    #
        # ------------------------------------------------------------ #
        print("\nP1d: high platelet count - remove thrombocytosis disorder")
        d = del_edge(s, "high platelet count", "6631009")
        print(f"     Deleted thrombocytosis edge: {d}")

        # ------------------------------------------------------------ #
        # P4 - "stopped Diannette a year ago" conf=0.6 - not a concept  #
        # ------------------------------------------------------------ #
        print("\nP4: Delete 'stopped Diannette a year ago' (not a clinical concept)")
        d = del_node(s, "stopped Diannette a year ago")
        print(f"     Deleted node: {d}")

        # ------------------------------------------------------------ #
        # P3 - Delete all 307 orphan SurfaceForm nodes                   #
        # ------------------------------------------------------------ #
        print("\nP3: Delete orphan SurfaceForm nodes (no MAPS_TO edge)")
        rows = list(s.run(_DETACH_ORPHANS))
        orphans_deleted = rows[0]["deleted"] if rows else 0
        print(f"     Deleted: {orphans_deleted} orphan nodes")

    driver.close()

    # ------------------------------------------------------------------ #
    # Verify the critical fixes via resolver                              #
    # ------------------------------------------------------------------ #
    print("\nVerification via live resolver:")
    checks = [
        ("atypical depression", "426566006"),
        ("Atypical depression", "426566006"),
        ("separation anxiety", "9855006"),
        ("Emphysema", "87433001"),
        ("Past COPD", "270473001"),
        ("high platelet count", "415115007"),
    ]
    try:
        resp = requests.post(
            "http://localhost:8001/terminology/resolve",
            json={"terms": [t for t, _ in checks], "top_k": 1},
            timeout=60,
        )
        if resp.ok:
            results = resp.json().get("results", {})
            passed = 0
            for term, expected in checks:
                candidates = results.get(term, [])
                got = candidates[0].get("snomed_concept_id") if candidates else "?"
                got_term = (candidates[0].get("snomed_term") or "?")[:50] if candidates else "?"
                status = "PASS" if got == expected else "FAIL"
                if status == "PASS":
                    passed += 1
                    print(f"  [PASS] {term!r} -> {got}")
                else:
                    print(f"  [FAIL] {term!r}")
                    print(f"         got={got} | {got_term}")
                    print(f"         want={expected}")
            print(f"\n  {passed}/{len(checks)} passed")
        else:
            print(f"  Resolver {resp.status_code}")
    except Exception as exc:
        print(f"  Resolver check skipped: {exc}")


if __name__ == "__main__":
    main()
