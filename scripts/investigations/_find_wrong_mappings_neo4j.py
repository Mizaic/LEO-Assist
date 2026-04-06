"""Look in Neo4j for SurfaceForm nodes and MAPS_TO relationships that explain
why 'NAFLD' and 'type 2 diabetes' resolve to wrong concepts.

The root cause: UPSERT_SURFACE_FORM_MAPPING creates additional MAPS_TO rels
without deleting existing ones. Multiple rels can exist; highest confidence wins.
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

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password))

FORMS = ["nafld", "type 2 diabetes"]


def run(query, **params):
    with driver.session() as s:
        return list(s.run(query, **params))


print("=== All SurfaceForm MAPS_TO relationships for problem terms ===")
for form in FORMS:
    rows = run(
        """
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE toLower(sf.normalized) = $form
        RETURN sf.normalized AS norm,
               sf.form AS surface_form,
               c.id AS concept_id,
               c.fsn AS concept_fsn,
               m.confidence AS confidence,
               m.provenance AS provenance,
               m.created_by AS created_by,
               m.approved_at AS approved_at
        ORDER BY m.confidence DESC
        """,
        form=form,
    )
    print(f"\n  '{form}' -> {len(rows)} MAPS_TO relationship(s):")
    if not rows:
        print("    (none found)")
    for r in rows:
        print(f"    concept={r['concept_id']}  confidence={r['confidence']}  "
              f"provenance={r['provenance']}  fsn={str(r['concept_fsn'])[:60]}")

print()
print("=== FIX: Delete wrong MAPS_TO relationships ===")
FIXES = [
    # (normalized_form, wrong_concept_id_to_delete)
    ("nafld",           "161535005"),   # History of liver disease - wrong
    ("type 2 diabetes", "410657003"),   # Type (attribute) - completely wrong
]
for form, wrong_cid in FIXES:
    rows = run(
        """
        MATCH (sf:SurfaceForm {normalized: $form})-[m:MAPS_TO]->(c:Concept {id: $cid})
        DELETE m
        RETURN count(m) AS deleted
        """,
        form=form,
        cid=wrong_cid,
    )
    deleted = rows[0]["deleted"] if rows else 0
    print(f"  Deleted {deleted} MAPS_TO: '{form}' -> [{wrong_cid}]")

print()
print("=== Remaining MAPS_TO relationships after fix ===")
for form in FORMS:
    rows = run(
        """
        MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
        WHERE toLower(sf.normalized) = $form
        RETURN c.id AS concept_id, m.confidence AS confidence, c.fsn AS fsn
        ORDER BY m.confidence DESC
        """,
        form=form,
    )
    print(f"\n  '{form}':")
    for r in rows:
        print(f"    [{r['concept_id']}] confidence={r['confidence']}  {str(r['fsn'])[:60]}")

driver.close()
print("\nDone.")
