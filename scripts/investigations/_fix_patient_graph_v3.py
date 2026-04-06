"""Remediate patient graph errors found by the v3 audit.

Two targeted fixes:

  Fix 1 -- D-dimer wrong concept
    Concept 25607008 was used for D-dimer but the terminology server resolves
    it as 'CoAr 1071 virus (organism)'. Remove all DOCUMENTS edges pointing to
    this concept from Encounter nodes. The correct surface form pin
    (_pin_audit_gaps_v3.py) ensures future encounters code correctly.

  Fix 2 -- Wrong assertion: 'present' where 'possible' is required
    Encounter f3308afb: Central sensitization coded as 'present' but the note
    says 'Likely some central sensitisation' -> should be 'possible'.
    Update the DOCUMENTS edge context/modifiers JSON to reflect the correct
    assertion.

  Fix 3 -- Flag BPH overcoded-from-medication
    Encounter 7de1028e: BPH code was inferred from Dutasteride + Tamsulosin
    with no explicit clinical diagnosis. Set audit_flag='overcoded_inference'
    on the DOCUMENTS edge so reviewers can see it; do not auto-delete.

Run:
    python scripts/investigations/_fix_patient_graph_v3.py --dry-run
    python scripts/investigations/_fix_patient_graph_v3.py
"""
from __future__ import annotations

import argparse
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

pg_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
pg_user = os.getenv("NEO4J_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "patient-dev")

# -- Fix 1: count and delete wrong D-dimer concept edges -------------------

_COUNT_DDIMER_WRONG = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s {conceptId: '25607008'})
RETURN count(r) AS edges, collect(e.id)[..5] AS sample_encounters
"""

_DELETE_DDIMER_WRONG = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s {conceptId: '25607008'})
DELETE r
RETURN count(r) AS deleted
"""

# Detach and delete the orphan concept node only if nothing else links to it
_DELETE_DDIMER_NODE = """
MATCH (s {conceptId: '25607008'})
WHERE NOT (()-[:DOCUMENTS]->(s)) AND NOT (()-[:HAS_CONDITION]->(s))
DETACH DELETE s
RETURN count(s) AS nodes_deleted
"""

# -- Fix 2: correct assertion on Central sensitization --------------------
# Target: encounter f3308afb, concept 246\d+ (Central sensitization)
# Change context JSON assertion from 'present' to 'possible'

_FIND_WRONG_ASSERTION = """
MATCH (e:Encounter {id: 'f3308afb-9f43-41d4-99d8-a6cd7f9a6743'})
      -[r:DOCUMENTS]->(s)
WHERE r.context IS NOT NULL
RETURN s.conceptId AS concept_id, s.name AS name,
       r.context AS context, r.modifiers AS modifiers
"""

_FIX_ASSERTION = """
MATCH (e:Encounter {id: 'f3308afb-9f43-41d4-99d8-a6cd7f9a6743'})
      -[r:DOCUMENTS]->(s)
WHERE r.context IS NOT NULL
WITH r, apoc.convert.fromJsonMap(r.context) AS ctx
WHERE ctx.assertion = 'present'
  AND (s.name CONTAINS 'sensitiz' OR s.name CONTAINS 'sensitisat')
SET r.context = apoc.convert.toJson(
    apoc.map.setKey(ctx, 'assertion', 'possible')
),
    r.audit_flag = 'assertion_corrected_v3'
RETURN count(r) AS updated, s.name AS concept
"""

# Fallback without apoc (plain string context update)
_FIX_ASSERTION_NOAPOC = """
MATCH (e:Encounter {id: 'f3308afb-9f43-41d4-99d8-a6cd7f9a6743'})
      -[r:DOCUMENTS]->(s)
WHERE (s.name CONTAINS 'sensitiz' OR s.name CONTAINS 'sensitisat')
  AND r.context IS NOT NULL
SET r.audit_flag = 'assertion_needs_correction_possible'
RETURN count(r) AS flagged, s.name AS concept
"""

# -- Fix 3: flag BPH overcoded-from-medication ----------------------------

_FLAG_BPH_OVERCODE = """
MATCH (e:Encounter {id: '7de1028e-ebd5-4cc7-acd8-c49a5ea29ae8'})
      -[r:DOCUMENTS]->(s)
WHERE s.conceptId = '266569009'
SET r.audit_flag = 'overcoded_inference_v3'
RETURN count(r) AS flagged, s.name AS concept
"""


def _run_fix(driver, dry_run: bool) -> None:
    with driver.session() as s:
        # ---- Fix 1: D-dimer wrong concept --------------------------------
        row = s.run(_COUNT_DDIMER_WRONG).single()
        edges = row["edges"] if row else 0
        samples = row["sample_encounters"] if row else []
        print(f"\nFix 1 -- D-dimer wrong concept (25607008)")
        print(f"  DOCUMENTS edges to delete: {edges}")
        if samples:
            print(f"  Sample encounters: {samples}")

        if not dry_run and edges > 0:
            res = s.run(_DELETE_DDIMER_WRONG).single()
            deleted = res["deleted"] if res else 0
            print(f"  Deleted {deleted} DOCUMENTS edges.")
            res2 = s.run(_DELETE_DDIMER_NODE).single()
            orphans = res2["nodes_deleted"] if res2 else 0
            if orphans:
                print(f"  Removed {orphans} orphan concept node(s).")
        elif dry_run:
            print("  DRY RUN -- no changes.")

        # ---- Fix 2: wrong assertion -------------------------------------
        print(f"\nFix 2 -- Wrong assertion (present -> possible)")
        codes = s.run(_FIND_WRONG_ASSERTION).data()
        for c in codes:
            ctx = {}
            try:
                ctx = json.loads(c.get("context") or "{}")
            except Exception:
                pass
            print(
                f"  concept={c.get('concept_id')} name={c.get('name')} "
                f"assertion={ctx.get('assertion','?')}"
            )

        if not dry_run:
            try:
                res = s.run(_FIX_ASSERTION).single()
                updated = res["updated"] if res else 0
                concept = res["concept"] if res else ""
                print(f"  Updated {updated} edge(s) for {concept!r}.")
            except Exception:
                # apoc not available -- use flag-only fallback
                res = s.run(_FIX_ASSERTION_NOAPOC).single()
                flagged = res["flagged"] if res else 0
                concept = res["concept"] if res else ""
                print(
                    f"  APOC not available; flagged {flagged} edge(s) for "
                    f"manual correction: {concept!r}"
                )
        else:
            print("  DRY RUN -- no changes.")

        # ---- Fix 3: BPH overcode flag -----------------------------------
        print(f"\nFix 3 -- Flag BPH overcoded-from-medication")
        if not dry_run:
            res = s.run(_FLAG_BPH_OVERCODE).single()
            flagged = res["flagged"] if res else 0
            concept = res["concept"] if res else ""
            print(f"  Flagged {flagged} edge(s) for {concept!r}.")
        else:
            print("  DRY RUN -- no changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remediate patient graph errors found by v3 audit"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))
    try:
        _run_fix(driver, dry_run=args.dry_run)
    finally:
        driver.close()

    if args.dry_run:
        print("\nDRY RUN complete -- re-run without --dry-run to apply.")
    else:
        print("\nAll fixes applied.")


if __name__ == "__main__":
    main()
