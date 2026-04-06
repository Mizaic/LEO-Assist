"""Search the KG for all 'Seen in fast track' specialist visit concepts.

Searches by text pattern so we find the actual IDs regardless of what concept
ID was assumed. Also checks the patient graph for any already-coded concepts
in DOCUMENTS relationships on encounters with fast-track text.

Run:
    python scripts/investigations/_find_fast_track_specialist_concepts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

# -- Search KG by term text --
_Q_KG_TEXT = """
MATCH (c:Concept)
WHERE toLower(coalesce(c.preferredTerm, c.id, '')) CONTAINS 'fast track'
   OR toLower(coalesce(c.preferredTerm, c.id, '')) CONTAINS 'seen in fast'
   OR toLower(coalesce(c.preferredTerm, c.id, '')) CONTAINS '2ww'
RETURN c.id AS id,
       coalesce(c.preferredTerm, c.id) AS term,
       c.semanticTag AS tag,
       c.active AS active
ORDER BY term
"""

# -- Also search by synonym/description --
_Q_KG_DESC = """
MATCH (c:Concept)-[:HAS_DESCRIPTION]->(d)
WHERE toLower(coalesce(d.term, '')) CONTAINS 'fast track'
  AND toLower(coalesce(d.term, '')) CONTAINS 'seen'
RETURN DISTINCT c.id AS id,
       coalesce(c.preferredTerm, c.id) AS preferred_term,
       d.term AS matched_term,
       c.semanticTag AS tag,
       c.active AS active
ORDER BY preferred_term
"""

# -- Check what concepts are already coded in patient graph for fast-track encounters --
_Q_PG_CODED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c)
WHERE toLower(coalesce(e.text, '') + ' ' + coalesce(e.note, '')) CONTAINS 'seen in fast track'
RETURN DISTINCT
    c.conceptId AS concept_id,
    c.name AS name,
    labels(c) AS labels,
    count(DISTINCT e) AS encounter_count
ORDER BY encounter_count DESC
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()

    print("=" * 70)
    print("KG search -- preferred term contains 'fast track' or 'seen in fast'")
    print("=" * 70)
    try:
        rows = kg.run(_Q_KG_TEXT)
        if rows:
            for r in rows:
                active = "active" if r.get("active") else "INACTIVE"
                print(f"  [{active}] {r['id']:20s}  {r['term']}")
                if r.get("tag"):
                    print(f"           tag: {r['tag']}")
        else:
            print("  (no results via preferred term search)")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("=" * 70)
    print("KG search -- description/synonym contains 'fast track' + 'seen'")
    print("=" * 70)
    try:
        rows2 = kg.run(_Q_KG_DESC)
        if rows2:
            for r in rows2:
                active = "active" if r.get("active") else "INACTIVE"
                print(f"  [{active}] {r['id']:20s}  {r['preferred_term']}")
                print(f"           matched: {r['matched_term']}")
        else:
            print("  (no description matches -- KG may not have synonym nodes)")
    except Exception as exc:
        print(f"  ERROR (description search): {exc}")
    finally:
        kg.close()

    print()
    print("=" * 70)
    print("Patient graph -- concepts already coded on fast-track encounters")
    print("=" * 70)
    try:
        rows3 = pg.run(_Q_PG_CODED)
        if rows3:
            for r in rows3:
                print(
                    f"  conceptId={r['concept_id']:20s}  "
                    f"encounters={r['encounter_count']:3d}  "
                    f"{r['name']}"
                )
        else:
            print("  (none -- no fast-track encounters have DOCUMENTS yet)")
    except Exception as exc:
        print(f"  ERROR: {exc}")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
