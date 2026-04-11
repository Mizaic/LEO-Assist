"""Audit and deduplicate SurfaceForm -> Concept mappings in the Knowledge Graph.

The coding-training bug may have persisted the same surface form mapped to
multiple Concept nodes (or the same concept via multiple MAPS_TO edges).
The unique constraint on SurfaceForm.normalized prevents node-level dupes, but
duplicate MAPS_TO relationships are not constrained.

Two passes:
  1. AUDIT  — report every SurfaceForm with more than one MAPS_TO rel.
  2. DEDUP  — for each such form, delete all but the highest-confidence rel.

Run with --dry-run to inspect without writing.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher — pulled from libs.cypher.terminology_queries canonical source
# ---------------------------------------------------------------------------

AUDIT_SURFACE_FORM_DUPLICATES = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, count(DISTINCT c) AS concept_count, count(r) AS rel_count
WHERE rel_count > 1
WITH sf, concept_count, rel_count
MATCH (sf)-[r:MAPS_TO]->(c:Concept)
RETURN sf.normalized       AS normalized,
       sf.form             AS form,
       concept_count,
       rel_count,
       collect({
           concept_id:  c.id,
           concept_fsn: c.fsn,
           confidence:  r.confidence,
           provenance:  r.provenance
       }) AS mappings
ORDER BY rel_count DESC, sf.form
LIMIT 200
"""

DEDUPLICATE_SURFACE_FORM_RELS = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, collect({r: r, confidence: coalesce(r.confidence, 0.0)}) AS all_rels
WHERE size(all_rels) > 1
WITH sf, all_rels,
     reduce(best = all_rels[0], x IN all_rels |
       CASE WHEN x.confidence > best.confidence THEN x ELSE best END
     ) AS keeper
UNWIND all_rels AS entry
WITH entry.r AS r, keeper
WHERE r <> keeper.r
DELETE r
RETURN count(r) AS duplicates_removed
"""

COUNT_DUPLICATE_SURFACE_FORM_RELS = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, count(r) AS rel_count
WHERE rel_count > 1
RETURN sum(rel_count - 1) AS excess_rels,
       count(sf)          AS affected_nodes
"""


def _load_creds() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        log.error(
            "Missing knowledge-graph Neo4j credentials. "
            "Set KNOWLEDGE_GRAPH_NEO4J_URI / _USERNAME / _PASSWORD in secrets/.env"
        )
        sys.exit(1)
    return uri, user, password


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit only — report duplicates without deleting anything.",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write audit CSV to this path (default: stdout JSON summary).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING"),
    )
    return p.parse_args()


def _audit(session) -> list[dict]:
    log.info("Running audit query …")
    records = list(session.run(AUDIT_SURFACE_FORM_DUPLICATES))
    rows = []
    for r in records:
        rows.append(
            {
                "normalized": r["normalized"],
                "form": r["form"],
                "concept_count": r["concept_count"],
                "rel_count": r["rel_count"],
                "mappings": r["mappings"],
            }
        )
    return rows


def _count_excess(session) -> tuple[int, int]:
    r = session.run(COUNT_DUPLICATE_SURFACE_FORM_RELS).single()
    if r is None:
        return 0, 0
    return int(r["excess_rels"] or 0), int(r["affected_nodes"] or 0)


def _print_audit_summary(rows: list[dict]) -> None:
    if not rows:
        log.info("No duplicate surface-form mappings found.")
        return
    log.warning("Found %d surface forms with duplicate MAPS_TO rels:", len(rows))
    for row in rows:
        mappings_fmt = "; ".join(
            f"{m.get('concept_id')} ({m.get('concept_fsn')}) conf={m.get('confidence')}"
            for m in (row["mappings"] or [])
        )
        log.warning(
            "  %-40s  rel_count=%d  concept_count=%d  → %s",
            repr(row["form"]),
            row["rel_count"],
            row["concept_count"],
            mappings_fmt,
        )


def _write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "normalized",
                "form",
                "concept_count",
                "rel_count",
                "mappings_json",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "normalized": row["normalized"],
                    "form": row["form"],
                    "concept_count": row["concept_count"],
                    "rel_count": row["rel_count"],
                    "mappings_json": json.dumps(row["mappings"]),
                }
            )
    log.info("Audit CSV written to %s", path)


def main() -> None:
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level)

    uri, user, password = _load_creds()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # ── Step 1: count excess rels ────────────────────────────────────
            excess_rels, affected_nodes = _count_excess(session)
            log.info(
                "Pre-run: %d affected SurfaceForm nodes, %d excess MAPS_TO rels",
                affected_nodes,
                excess_rels,
            )

            # ── Step 2: audit ────────────────────────────────────────────────
            audit_rows = _audit(session)
            _print_audit_summary(audit_rows)

            if args.report:
                _write_csv(audit_rows, args.report)

            if not audit_rows:
                print(
                    json.dumps(
                        {
                            "status": "clean",
                            "affected_nodes": 0,
                            "excess_rels": 0,
                            "duplicates_removed": 0,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        indent=2,
                    )
                )
                return

            if args.dry_run:
                log.info("--dry-run: skipping deduplication write.")
                print(
                    json.dumps(
                        {
                            "status": "dry_run",
                            "affected_nodes": affected_nodes,
                            "excess_rels": excess_rels,
                            "duplicates_removed": 0,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        indent=2,
                    )
                )
                return

            # ── Step 3: deduplicate ──────────────────────────────────────────
            log.info(
                "Running deduplication (keeping highest-confidence MAPS_TO per SF) …"
            )
            result = session.run(DEDUPLICATE_SURFACE_FORM_RELS).single()
            removed = int((result or {}).get("duplicates_removed", 0))
            log.info(
                "Deduplication complete — %d excess MAPS_TO rels removed.", removed
            )

            # ── Step 4: post-run verification ────────────────────────────────
            excess_after, nodes_after = _count_excess(session)
            log.info(
                "Post-run: %d affected SurfaceForm nodes, %d excess rels remain",
                nodes_after,
                excess_after,
            )
            if excess_after > 0:
                log.warning(
                    "%d excess rels still remain — this may indicate multi-concept "
                    "ambiguity that requires manual review (see CSV report).",
                    excess_after,
                )

            print(
                json.dumps(
                    {
                        "status": "ok",
                        "affected_nodes_before": affected_nodes,
                        "excess_rels_before": excess_rels,
                        "duplicates_removed": removed,
                        "excess_rels_after": excess_after,
                        "affected_nodes_after": nodes_after,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=2,
                )
            )

    finally:
        driver.close()


if __name__ == "__main__":
    main()
