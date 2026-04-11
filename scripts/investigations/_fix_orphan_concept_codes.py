"""Migrate retired/orphaned SNOMED codes in encounter Disease nodes to active replacements.

Plan:
  269457002 Malignant neoplasm of esophagus NOS  -> 363402007 Malignant neoplasm of esophagus
  255080008 Carcinoma of stomach                 -> 363349007 Malignant neoplasm of stomach

Then delete the orphan :Concept nodes for the retired codes.

Run with --dry-run (default) to preview changes, --apply to execute.
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

DRY_RUN = "--apply" not in sys.argv
CANCER_ROOT = "363346000"

MIGRATIONS = [
    {
        "old_id": "269457002",
        "old_name": "Malignant neoplasm of esophagus NOS (disorder)",
        "new_id": "363402007",
        "new_name": "Malignant neoplasm of esophagus (disorder)",
    },
    {
        "old_id": "255080008",
        "old_name": "Carcinoma of stomach (disorder)",
        "new_id": "363349007",
        "new_name": "Malignant neoplasm of stomach (disorder)",
    },
]

_Q_CHECK_NEW_IN_HIERARCHY = """
MATCH (c:Concept {id: $cid})-[:IS_A*1..5]->(root:Concept {id: $root})
RETURN count(*) > 0 AS ok
"""

_Q_COUNT_OLD = """
MATCH (c)
WHERE c.conceptId = $old_id_int
  AND NOT 'Concept' IN labels(c)
RETURN count(c) AS cnt, labels(c)[0] AS lbl
"""

_Q_UPDATE_DISEASE_NODES = """
MATCH (c)
WHERE c.conceptId = $old_id_int
  AND NOT 'Concept' IN labels(c)
SET c.conceptId = $new_id_int,
    c.name      = $new_name
RETURN count(c) AS updated
"""

_Q_DELETE_ORPHAN_CONCEPT = """
MATCH (c:Concept {id: $old_id})
WHERE NOT EXISTS { MATCH (c)-[:IS_A]-() }
  AND NOT EXISTS { MATCH ()-[:IS_A]->(c) }
DETACH DELETE c
RETURN count(c) AS deleted
"""

_Q_CHECK_ORPHAN_CONCEPT = """
MATCH (c:Concept {id: $old_id})
RETURN c.id AS id, c.active AS active, c.fsn AS fsn,
       EXISTS { MATCH (c)-[:IS_A]-() } AS has_isa_out,
       EXISTS { MATCH ()-[:IS_A]->(c) } AS has_isa_in
"""


def main() -> None:
    mode = "DRY RUN (preview only)" if DRY_RUN else "*** APPLYING CHANGES ***"
    print(f"Mode: {mode}")
    print(f"Pass --apply to execute changes.\n")

    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        for m in MIGRATIONS:
            old_id = m["old_id"]
            new_id = m["new_id"]
            old_id_int = int(old_id)
            new_id_int = int(new_id)

            print(f"{'='*70}")
            print(f"Migrating: {old_id} -> {new_id}")
            print(f"  {m['old_name']}")
            print(f"  -> {m['new_name']}")

            # 1. Verify new code is in cancer hierarchy
            ok = kg.run(_Q_CHECK_NEW_IN_HIERARCHY, cid=new_id, root=CANCER_ROOT)
            in_hier = ok[0]["ok"] if ok else False
            print(f"  New code in cancer IS_A hierarchy: {in_hier}")
            if not in_hier:
                print(
                    f"  WARNING: {new_id} is not a descendant of {CANCER_ROOT} -- skipping"
                )
                continue

            # 2. Count Disease/Clinical_finding nodes using old code
            with pg.session() as s:
                counts = s.run(_Q_COUNT_OLD, old_id_int=old_id_int).data()
            total = sum(r["cnt"] for r in counts)
            print(f"  Nodes to update: {total}")
            for r in counts:
                if r["cnt"] > 0:
                    print(f"    {r['lbl']}: {r['cnt']}")

            # 3. Check orphan Concept node
            orphan = kg.run(_Q_CHECK_ORPHAN_CONCEPT, old_id=old_id)
            if orphan:
                o = orphan[0]
                print(
                    f"  Orphan :Concept node: active={o['active']}, "
                    f"isa_out={o['has_isa_out']}, isa_in={o['has_isa_in']}"
                )
                is_orphan = not o["has_isa_out"] and not o["has_isa_in"]
                print(f"  Safe to delete orphan: {is_orphan}")
            else:
                is_orphan = False
                print(f"  No :Concept node found for {old_id}")

            if not DRY_RUN:
                # 4. Update Disease nodes
                with pg.session() as s:
                    res = s.run(
                        _Q_UPDATE_DISEASE_NODES,
                        old_id_int=old_id_int,
                        new_id_int=new_id_int,
                        new_name=m["new_name"],
                    ).single()
                    updated = res["updated"] if res else 0
                print(f"  Updated {updated} Disease/Clinical_finding nodes")

                # 5. Delete orphan Concept node
                if is_orphan:
                    res2 = kg.run(_Q_DELETE_ORPHAN_CONCEPT, old_id=old_id)
                    deleted = res2[0]["deleted"] if res2 else 0
                    print(f"  Deleted {deleted} orphan :Concept node(s)")
            else:
                print(f"  [DRY RUN] Would update {total} Disease nodes")
                if is_orphan:
                    print(f"  [DRY RUN] Would delete orphan :Concept node for {old_id}")

            print()

        print("Done.")
        if DRY_RUN:
            print("Re-run with --apply to execute.")

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
