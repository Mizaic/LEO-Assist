"""Diagnose whether IS_A expansion is working for the cancer_audit domain."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient

DOMAIN_ID = "cancer_audit"

_Q_VALUESETS = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "RETURN v.id AS id, v.rawJson AS raw_json"
)

_Q_CONCEPT_PROPS = """
MATCH (c:Concept)
RETURN keys(c) AS props, labels(c) AS lbls
LIMIT 1
"""

_Q_CONCEPT_BY_ID = """
MATCH (c:Concept {id: $cid})
RETURN c.id AS id, c.conceptId AS conceptId, c.code AS code, c.preferredTerm AS term
LIMIT 1
"""

_Q_ISA_EXPANSION = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id, "
    "       coalesce(d.preferredTerm, d.id) AS display"
)

_Q_ISA_ANY = """
MATCH (a)-[:IS_A]->(b)
RETURN labels(a) AS a_lbl, labels(b) AS b_lbl,
       keys(a) AS a_keys, a.id AS a_id, b.id AS b_id
LIMIT 3
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    try:
        print("=== ValueSets in cancer_audit ===")
        rows = kg.run(_Q_VALUESETS, domain_id=DOMAIN_ID)
        parent_ids = []
        for r in rows or []:
            vid = r["id"]
            raw = r.get("raw_json")
            if not raw:
                print(f"  {vid}: NO rawJson")
                continue
            vs = json.loads(raw) if isinstance(raw, str) else raw
            concepts = [
                c for inc in (vs.get("compose") or {}).get("include") or []
                for c in inc.get("concept") or []
            ]
            print(f"  {vid}: {len(concepts)} explicit concepts in compose.include.concept")
            for c in concepts:
                code = c.get("code", "")
                display = c.get("display", "")
                print(f"    code={code!r:20s} display={display!r}")
                parent_ids.append(code)

        print()
        print(f"Parent IDs collected for IS_A expansion: {parent_ids}")

        print()
        print("=== IS_A relationships in graph (any) ===")
        isa_any = kg.run(_Q_ISA_ANY)
        if isa_any:
            for r in isa_any:
                print(f"  ({r['a_lbl']}) id={r['a_id']} -[:IS_A]-> ({r['b_lbl']}) id={r['b_id']}")
        else:
            print("  NONE found -- no IS_A relationships exist in graph!")

        print()
        print("=== Concept node properties ===")
        props = kg.run(_Q_CONCEPT_PROPS)
        if props:
            print(f"  labels: {props[0]['lbls']}, keys: {props[0]['props']}")
        else:
            print("  No Concept nodes found at all!")

        if parent_ids:
            print()
            print("=== IS_A expansion query result ===")
            desc = kg.run(_Q_ISA_EXPANSION, ids=parent_ids)
            print(f"  Descendants found: {len(desc or [])}")
            for r in (desc or [])[:10]:
                print(f"  {r['parent_id']} -> {r['child_id']}  {r.get('display','')}")

            print()
            print("=== Lookup concept by id directly ===")
            for cid in parent_ids[:3]:
                row = kg.run(_Q_CONCEPT_BY_ID, cid=cid)
                if row:
                    print(f"  id={cid!r} -> {row[0]}")
                else:
                    print(f"  id={cid!r} -> NOT FOUND in :Concept nodes")

    finally:
        kg.close()


if __name__ == "__main__":
    main()
