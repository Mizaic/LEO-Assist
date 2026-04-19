"""Rewire legacy guidance :SnomedConcept nodes onto canonical :Concept.

DI-LEO-AI-528 / R-LEO-AI-508.

The v1 guidance rule generator used to MERGE every coded criterion / action /
applies_to concept as a parallel `(:SnomedConcept {conceptId})` node, sitting
beside the canonical SNOMED loader's `(:Concept {id})`. That schema split
caused two real bugs:

  1. /admin/guidance edits failed with "Unknown SNOMED concept ids" because
     the verifier only looked at `:Concept` and FE-picker concepts only
     existed under one label.
  2. The bitmap compiler's `_closure_ids` walked IS_A on `:SnomedConcept`,
     which the generator NEVER wrote -- so descendant expansion silently
     fell back to exact-match for every guidance-only concept.

DI-LEO-AI-528 unified writes onto canonical `:Concept`. This script rewires
existing legacy guidance edges onto canonical nodes so the dual-graph
fallback in `_VERIFY_CONCEPTS` can eventually be removed.

CRITICAL SAFETY:
  * The patient coding subgraph (libs/cypher/documents_queries.py) ALSO
    writes `(:SnomedConcept {conceptId})` for every patient-coded SNOMED
    finding, connected via `:DOCUMENTS`. Those nodes MUST NOT be touched.
    Every legacy-node selector below is gated on
    `NOT (legacy)<-[:DOCUMENTS]-()` so patient data is invisible to this
    migration.
  * The script is idempotent: re-running produces no new writes (every
    canonical MERGE / edge MERGE is content-addressed).
  * Dry-run mode is the default safe path; --apply must be passed
    explicitly to mutate the graph.

Usage:

    source .venv/bin/activate
    python -m scripts.migrations.2026_link_or_delete_orphan_snomed_concepts --dry-run
    python -m scripts.migrations.2026_link_or_delete_orphan_snomed_concepts --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Guidance-subgraph relationship types. Only legacy :SnomedConcept nodes
# reached via these edges are rewired; everything else (notably :DOCUMENTS
# from the patient subgraph) is left untouched.
GUIDANCE_REL_TYPES: tuple[str, ...] = (
    "HAS_CRITERIA",
    "HAS_ACTION",
    "APPLIES_TO",
    "INCLUDES_CONCEPT",
)


# -- Cypher --------------------------------------------------------------------

# Count guidance-subgraph legacy nodes pre/post for the operator summary.
# Excludes patient-coding nodes via the :DOCUMENTS guard.
_COUNT_GUIDANCE_LEGACY = """
MATCH (legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND (
    (legacy)<-[:HAS_CRITERIA]-()    OR
    (legacy)<-[:HAS_ACTION]-()      OR
    (legacy)<-[:APPLIES_TO]-()      OR
    (legacy)<-[:INCLUDES_CONCEPT]-()
  )
RETURN count(legacy) AS n
"""


# MERGE the canonical twin for every guidance legacy node and copy display
# properties when the canonical is freshly created. Idempotent because:
#   - MERGE on (:Concept {id}) creates at most one twin per legacy.conceptId.
#   - The ON CREATE SET only fires the first time; subsequent runs leave the
#     existing canonical row untouched.
_MERGE_CANONICAL_TWINS = """
MATCH (legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND (
    (legacy)<-[:HAS_CRITERIA]-()    OR
    (legacy)<-[:HAS_ACTION]-()      OR
    (legacy)<-[:APPLIES_TO]-()      OR
    (legacy)<-[:INCLUDES_CONCEPT]-()
  )
  AND legacy.conceptId IS NOT NULL
WITH legacy
MERGE (canonical:Concept {id: legacy.conceptId})
ON CREATE SET
  canonical.preferred_term = coalesce(legacy.term, legacy.conceptId),
  canonical.semantic_tag   = coalesce(legacy.semanticTag, ''),
  canonical.source         = 'guidance_migration_2026',
  canonical.createdAt      = datetime()
RETURN count(canonical) AS twins
"""


# Rewire one relationship type from legacy to canonical, preserving every
# edge property. APOC is intentionally NOT used so the script runs against
# any Neo4j Community deployment.
#
# The rewire is idempotent because:
#   - The canonical edge is MERGEd (not CREATEd), so a second pass finds
#     the existing edge instead of inserting a duplicate.
#   - The legacy edge is DELETEd, so a second pass finds nothing to migrate.
#
# We intentionally re-MATCH the legacy node inside each statement instead
# of carrying it across UNWIND boundaries -- this keeps each batch self-
# contained and lets the operator interrupt safely between rel-types.
_REWIRE_REL_TEMPLATE = """
MATCH (parent)-[r:{rel}]->(legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND legacy.conceptId IS NOT NULL
WITH parent, r, legacy, properties(r) AS props
MATCH (canonical:Concept {{id: legacy.conceptId}})
MERGE (parent)-[new_r:{rel}]->(canonical)
SET new_r += props
DELETE r
RETURN count(new_r) AS rewired
"""


# Delete legacy nodes that are now entirely orphaned by guidance and have
# no other relationships of any kind. The double guard (`NOT (legacy)--()`
# and the explicit `:DOCUMENTS` re-check) is belt-and-braces: even if a
# future relationship type were to be added between guidance and patient
# data, this query will refuse to delete nodes still in use.
_DELETE_ORPHANS = """
MATCH (legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND NOT (legacy)--()
  AND coalesce(legacy.source, '') IN ['guidance_rule_extraction', 'guidance_migration_2026', '']
DELETE legacy
RETURN count(legacy) AS deleted
"""


# Operator audit query: surface any guidance legacy nodes left behind after
# migration. A non-empty result means either:
#   a) The canonical loader does not have the SNOMED id (genuine data gap).
#   b) The legacy node has unexpected inbound relationships (regression).
# Either way the operator should investigate before declaring success.
_AUDIT_REMAINING = """
MATCH (legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND (
    (legacy)<-[:HAS_CRITERIA]-()    OR
    (legacy)<-[:HAS_ACTION]-()      OR
    (legacy)<-[:APPLIES_TO]-()      OR
    (legacy)<-[:INCLUDES_CONCEPT]-()
  )
RETURN legacy.conceptId AS concept_id, legacy.term AS term
ORDER BY legacy.conceptId
LIMIT 100
"""


# Dry-run counting -- never mutates. One query per relationship type so the
# operator sees how much of each kind of edge would be rewired.
_COUNT_REL_TEMPLATE = """
MATCH (parent)-[r:{rel}]->(legacy:SnomedConcept)
WHERE NOT (legacy)<-[:DOCUMENTS]-()
  AND legacy.conceptId IS NOT NULL
RETURN count(r) AS rewired
"""


@dataclass
class MigrationStats:
    pre_legacy_count: int = 0
    twins_merged: int = 0
    rels_rewired: dict[str, int] = None
    orphans_deleted: int = 0
    remaining_after: list[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.rels_rewired is None:
            self.rels_rewired = {}
        if self.remaining_after is None:
            self.remaining_after = []


def run_migration(session, *, apply: bool) -> MigrationStats:
    """Run the migration against an active Neo4j session.

    The function is split out so unit tests can drive it with a mocked
    session and assert the call sequence (idempotent + lossless) without
    needing a live Neo4j.
    """
    stats = MigrationStats()

    pre = session.run(_COUNT_GUIDANCE_LEGACY).single()
    stats.pre_legacy_count = int(pre["n"]) if pre else 0

    if not apply:
        # Dry-run: count what _would_ change but never write. We deliberately
        # use _COUNT_REL_TEMPLATE (a pure read) instead of trying to "preview"
        # the rewire query -- the rewire MERGEs / DELETEs and would mutate
        # the graph if executed.
        stats.twins_merged = stats.pre_legacy_count
        for rel in GUIDANCE_REL_TYPES:
            count_rel = session.run(_COUNT_REL_TEMPLATE.format(rel=rel)).single()
            stats.rels_rewired[rel] = int(count_rel["rewired"]) if count_rel else 0
        return stats

    twins = session.run(_MERGE_CANONICAL_TWINS).single()
    stats.twins_merged = int(twins["twins"]) if twins else 0

    for rel in GUIDANCE_REL_TYPES:
        rewired = session.run(_REWIRE_REL_TEMPLATE.format(rel=rel)).single()
        stats.rels_rewired[rel] = int(rewired["rewired"]) if rewired else 0

    deleted = session.run(_DELETE_ORPHANS).single()
    stats.orphans_deleted = int(deleted["deleted"]) if deleted else 0

    remaining = session.run(_AUDIT_REMAINING)
    stats.remaining_after = [dict(r) for r in remaining]
    return stats


def _print_summary(stats: MigrationStats, *, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] guidance :SnomedConcept legacy nodes: {stats.pre_legacy_count}")
    print(f"[{mode}] canonical :Concept twins (would be) merged: {stats.twins_merged}")
    for rel, n in stats.rels_rewired.items():
        print(f"[{mode}] {rel} edges (would be) rewired: {n}")
    if apply:
        print(f"[APPLY] orphan legacy nodes deleted: {stats.orphans_deleted}")
        if stats.remaining_after:
            print(
                f"[APPLY] WARNING: {len(stats.remaining_after)} guidance legacy "
                "nodes remain (first 100 listed):",
                file=sys.stderr,
            )
            for r in stats.remaining_after:
                print(
                    f"  - conceptId={r.get('concept_id')} term={r.get('term')!r}",
                    file=sys.stderr,
                )
        else:
            print("[APPLY] no guidance legacy nodes remain -- migration complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Mutate the graph"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only (default-safe)"
    )
    args = parser.parse_args(argv)

    if not args.apply and not args.dry_run:
        parser.error("Pass --dry-run or --apply explicitly.")

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive.")

    from dotenv import load_dotenv  # noqa: WPS433
    from neo4j import GraphDatabase  # noqa: WPS433

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)

    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD")
    )
    if not uri or not user or not password:
        print(
            "Missing Neo4j credentials in secrets/.env*; aborting.",
            file=sys.stderr,
        )
        return 2

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            stats = run_migration(session, apply=args.apply)
    finally:
        driver.close()

    _print_summary(stats, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
