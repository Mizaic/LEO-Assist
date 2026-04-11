"""Fix wrong GCL (guideline_config_loader) MAPS_TO edges directly in Neo4j.

Three targeted Cypher operations in priority order:

  1. DELETE GCL edges to INACTIVE concepts
     (concept.active = false -- stale SNOMED codes, always wrong)

  2. DELETE GCL edges to the broad catch-all Mental disorder concept
     (74732009) where a specific non-GCL mapping already exists.
     Where NO alternative exists, keep the edge but flag it.

  3. DELETE GCL SITUATION edges where a better disorder mapping already
     exists (concept.semantic_tag = 'situation' AND form does not start
     with a history/absence prefix).

  4. DELETE GCL edges to other known broad catch-all concepts where a
     better non-GCL mapping already exists.

All deletes are logged.  A dry-run mode is supported.

Usage
-----
  python scripts/investigations/_fix_knowledge_graph_mappings.py            # live
  python scripts/investigations/_fix_knowledge_graph_mappings.py --dry-run  # preview counts
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

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# ---------------------------------------------------------------------------
# Broad catch-all concept IDs that GCL wrongly uses as targets
# ---------------------------------------------------------------------------
_BROAD_CATCH_ALL = [
    "74732009",  # Mental disorder (disorder) -- used for 700+ specific MH terms
    "128462008",  # Metastatic malignant neoplasm (disorder)
    "372130007",  # Malignant neoplasm of skin (disorder)
]

# Situation concept IDs that GCL wrongly uses for active (non-historical) forms
# These are only removed when a better disorder mapping already exists.
_WRONG_SITUATION_IDS = [
    "267004000",  # History of musculoskeletal disease
    "275552000",  # History of kidney disease
    "308064009",  # History of cerebrovascular disease
    "270473001",  # History of chronic obstructive airway disease
    "472961001",  # History of disorder of connective tissue
    "161535005",  # History of liver disease
    "161465002",  # History of dementia
    "428269004",  # Family history of malignant neoplasm of trachea -- legitimate but wrong for active
]

# History/absence prefixes that make a situation code *correct* (don't delete these)
_OK_SITUATION_PREFIXES = (
    "history of ",
    "h/o ",
    "hx ",
    "hx. ",
    "no ",
    "not ",
    "never ",
    "absent ",
    "absence of ",
    "ex-smoker",
    "ex smoker",
    "former smoker",
    "family history",
    "fh of ",
)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# 1. Count + delete GCL edges to inactive concepts
_COUNT_INACTIVE = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.active = false
RETURN count(m) AS n
"""
_DELETE_INACTIVE = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.active = false
WITH sf, m, c
DELETE m
RETURN count(*) AS deleted, collect(DISTINCT sf.form)[..20] AS sample_forms
"""

# 2a. Count GCL broad-catch-all edges that have a better alternative
_COUNT_BROAD_WITH_ALT = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: $cid})
WHERE m.provenance = 'guideline_config_loader'
  AND EXISTS {
    MATCH (sf)-[m2:MAPS_TO]->(c2:Concept)
    WHERE m2.provenance <> 'guideline_config_loader'
      AND c2.active = true
  }
RETURN count(m) AS n
"""

# 2b. Delete GCL broad-catch-all edges that have a better alternative
_DELETE_BROAD_WITH_ALT = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: $cid})
WHERE m.provenance = 'guideline_config_loader'
  AND EXISTS {
    MATCH (sf)-[m2:MAPS_TO]->(c2:Concept)
    WHERE m2.provenance <> 'guideline_config_loader'
      AND c2.active = true
  }
DELETE m
RETURN count(*) AS deleted
"""

# 2c. Count GCL broad-catch-all edges with NO alternative (orphans - need new mapping)
_COUNT_BROAD_NO_ALT = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: $cid})
WHERE m.provenance = 'guideline_config_loader'
  AND NOT EXISTS {
    MATCH (sf)-[m2:MAPS_TO]->(c2:Concept)
    WHERE m2.provenance <> 'guideline_config_loader'
      AND c2.active = true
  }
RETURN count(m) AS n, collect(sf.form) AS forms
"""

# 3. Delete GCL situation edges where a better disorder mapping already exists
#    and the form text does NOT start with a history/absence prefix
_COUNT_SITUATION_WITH_ALT = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.semantic_tag = 'situation'
  AND c.id IN $situation_ids
  AND NOT any(prefix IN $ok_prefixes WHERE toLower(sf.form) STARTS WITH prefix)
  AND EXISTS {
    MATCH (sf)-[m2:MAPS_TO]->(c2:Concept)
    WHERE m2.provenance <> 'guideline_config_loader'
      AND c2.active = true
      AND c2.semantic_tag <> 'situation'
  }
RETURN count(m) AS n, collect(sf.form) AS forms
"""

_DELETE_SITUATION_WITH_ALT = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.semantic_tag = 'situation'
  AND c.id IN $situation_ids
  AND NOT any(prefix IN $ok_prefixes WHERE toLower(sf.form) STARTS WITH prefix)
  AND EXISTS {
    MATCH (sf)-[m2:MAPS_TO]->(c2:Concept)
    WHERE m2.provenance <> 'guideline_config_loader'
      AND c2.active = true
      AND c2.semantic_tag <> 'situation'
  }
DELETE m
RETURN count(*) AS deleted
"""

# 4. Remaining GCL situation edges with no good alternative (for report only)
_REMAINING_SITUATIONS = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.semantic_tag = 'situation'
  AND NOT any(prefix IN $ok_prefixes WHERE toLower(sf.form) STARTS WITH prefix)
RETURN sf.form AS form, sf.normalized AS normalized,
       c.id AS concept_id, c.fsn AS concept_fsn, m.confidence AS confidence
ORDER BY sf.form
"""


def _run(session, query: str, **params) -> list[dict]:
    return [dict(r) for r in session.run(query, **params)]


def main(dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"Connecting: {kg_uri}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        _fix_inactive(s, dry_run)
        _fix_broad_catch_all(s, dry_run)
        _fix_wrong_situations(s, dry_run)
        _report_remaining_situations(s)

    driver.close()
    print(f"\n[{mode}] Done.")


def _fix_inactive(session, dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print("1. GCL EDGES TO INACTIVE CONCEPTS")
    result = _run(session, _COUNT_INACTIVE)
    n = result[0]["n"] if result else 0
    print(f"   Found: {n} edges to inactive concepts")
    if n == 0:
        return
    if dry_run:
        print("   [DRY-RUN] Would delete these edges")
        return
    result = _run(session, _DELETE_INACTIVE)
    deleted = result[0]["deleted"] if result else 0
    sample = result[0].get("sample_forms", []) if result else []
    print(f"   Deleted: {deleted}")
    if sample:
        print(f"   Sample forms: {sample[:10]}")


def _fix_broad_catch_all(session, dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print("2. GCL EDGES TO BROAD CATCH-ALL CONCEPTS")
    total_deleted = 0
    total_orphans = 0
    orphan_forms: list[str] = []

    for cid in _BROAD_CATCH_ALL:
        r_with = _run(session, _COUNT_BROAD_WITH_ALT, cid=cid)
        n_with = r_with[0]["n"] if r_with else 0

        r_no = _run(session, _COUNT_BROAD_NO_ALT, cid=cid)
        n_no = r_no[0]["n"] if r_no else 0
        forms_no = r_no[0].get("forms", []) if r_no else []

        print(f"\n   Concept {cid}:")
        print(f"     {n_with} edges have a better alternative -> will DELETE")
        print(f"     {n_no} edges have NO alternative -> KEEP (need new mapping)")
        if forms_no:
            print(f"     Orphan forms (sample): {forms_no[:10]}")

        if not dry_run and n_with > 0:
            r_del = _run(session, _DELETE_BROAD_WITH_ALT, cid=cid)
            deleted = r_del[0]["deleted"] if r_del else 0
            print(f"     Deleted {deleted}")
            total_deleted += deleted

        total_orphans += n_no
        orphan_forms.extend(forms_no)

    print(f"\n   Total deleted: {total_deleted}")
    print(f"   Total orphans (kept, need new mapping): {total_orphans}")
    if orphan_forms:
        out_path = ROOT / "scripts" / "investigations" / "gcl_orphan_mental_forms.txt"
        out_path.write_text("\n".join(sorted(set(orphan_forms))), encoding="utf-8")
        print(f"   Orphan list written: {out_path}")


def _fix_wrong_situations(session, dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print("3. GCL SITUATION EDGES WITH BETTER DISORDER ALTERNATIVE")

    r_count = _run(
        session,
        _COUNT_SITUATION_WITH_ALT,
        situation_ids=_WRONG_SITUATION_IDS,
        ok_prefixes=list(_OK_SITUATION_PREFIXES),
    )
    n = r_count[0]["n"] if r_count else 0
    forms = r_count[0].get("forms", []) if r_count else []
    print(f"   Found: {n} GCL situation edges that have a better alternative")
    if forms:
        print(f"   Sample forms: {sorted(forms)[:20]}")

    if n == 0:
        return
    if dry_run:
        print("   [DRY-RUN] Would delete these edges")
        return
    r_del = _run(
        session,
        _DELETE_SITUATION_WITH_ALT,
        situation_ids=_WRONG_SITUATION_IDS,
        ok_prefixes=list(_OK_SITUATION_PREFIXES),
    )
    deleted = r_del[0]["deleted"] if r_del else 0
    print(f"   Deleted: {deleted}")


def _report_remaining_situations(session) -> None:
    print("\n" + "=" * 70)
    print("4. REMAINING GCL SITUATION EDGES (no good alternative - need attention)")
    rows = _run(
        session,
        _REMAINING_SITUATIONS,
        ok_prefixes=list(_OK_SITUATION_PREFIXES),
    )
    print(f"   {len(rows)} remaining situation edges without a better mapping")
    for r in rows[:30]:
        print(f"   {r['form']!r} -> {r['concept_id']} | {r['concept_fsn']}")
    if len(rows) > 30:
        print(f"   ... and {len(rows) - 30} more")
    if rows:
        out = ROOT / "scripts" / "investigations" / "gcl_remaining_situations.json"
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"   Written: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
