"""Import deterministic Read->SNOMED mappings into Neo4j.

Source JSONL rows are expected to contain:
  - read_code
  - read_term
  - snomed_code
  - mapping_status
  - mapping_source

Dry-run mode reports what would be matched/created without writing.
Apply mode:
  - MATCHes SNOMED :Concept by snomed_code
  - MERGEs :ReadCode by read_code
  - Adds/updates read term metadata
  - MERGEs (:Concept)-[:MAPS_TO_READ]->(:ReadCode)
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = (
    ROOT
    / "external_content"
    / "trud-snomed-data-migration"
    / "read_to_snomed.source_map.deterministic_only.jsonl"
)
DEFAULT_BATCH_SIZE = 5_000


@dataclass
class Stats:
    input_rows: int = 0
    skipped_rows: int = 0
    eligible_rows: int = 0
    concept_matches: int = 0
    concept_misses: int = 0
    read_existing: int = 0
    read_missing: int = 0
    rel_existing: int = 0
    rel_missing_with_existing_read: int = 0
    rel_needs_new_read: int = 0
    applied_rows: int = 0

    def merge(self, other: "Stats") -> None:
        self.input_rows += other.input_rows
        self.skipped_rows += other.skipped_rows
        self.eligible_rows += other.eligible_rows
        self.concept_matches += other.concept_matches
        self.concept_misses += other.concept_misses
        self.read_existing += other.read_existing
        self.read_missing += other.read_missing
        self.rel_existing += other.rel_existing
        self.rel_missing_with_existing_read += other.rel_missing_with_existing_read
        self.rel_needs_new_read += other.rel_needs_new_read
        self.applied_rows += other.applied_rows


def _load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError(
            "Missing KNOWLEDGE_GRAPH_NEO4J_URI / _USERNAME / _PASSWORD in env/secrets/.env"
        )
    return uri, user, password


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _to_row(rec: dict) -> dict | None:
    read_code = str(rec.get("read_code", "")).strip()
    snomed_code = str(rec.get("snomed_code", "")).strip()
    read_term = str(rec.get("read_term", "")).strip()
    mapping_status = str(rec.get("mapping_status", "")).strip()
    mapping_source = str(rec.get("mapping_source", "")).strip()

    if not read_code or not snomed_code:
        return None
    if mapping_status and mapping_status != "deterministic_source_map":
        return None

    return {
        "read_code": read_code,
        "read_term": read_term,
        "snomed_code": snomed_code,
        "mapping_status": mapping_status or "deterministic_source_map",
        "mapping_source": mapping_source or "dmwb_source_maps",
    }


DRY_RUN_QUERY = """
UNWIND $rows AS r
OPTIONAL MATCH (c:Concept {id: r.snomed_code})
OPTIONAL MATCH (rd:ReadCode {code: r.read_code})
OPTIONAL MATCH (c)-[m:MAPS_TO_READ]->(rd)
RETURN
  count(*) AS eligible_rows,
  sum(CASE WHEN c IS NOT NULL THEN 1 ELSE 0 END) AS concept_matches,
  sum(CASE WHEN c IS NULL THEN 1 ELSE 0 END) AS concept_misses,
  sum(CASE WHEN rd IS NOT NULL THEN 1 ELSE 0 END) AS read_existing,
  sum(CASE WHEN rd IS NULL THEN 1 ELSE 0 END) AS read_missing,
  sum(CASE WHEN c IS NOT NULL AND rd IS NOT NULL AND m IS NOT NULL THEN 1 ELSE 0 END) AS rel_existing,
  sum(CASE WHEN c IS NOT NULL AND rd IS NOT NULL AND m IS NULL THEN 1 ELSE 0 END) AS rel_missing_with_existing_read,
  sum(CASE WHEN c IS NOT NULL AND rd IS NULL THEN 1 ELSE 0 END) AS rel_needs_new_read
"""


APPLY_QUERY = """
UNWIND $rows AS r
MATCH (c:Concept {id: r.snomed_code})
MERGE (rd:ReadCode {code: r.read_code})
ON CREATE SET rd.created_by = "read_to_snomed_source_map"
SET rd.version = coalesce(rd.version, "ctv3"),
    rd.source_map_term = r.read_term,
    rd.term = CASE
      WHEN coalesce(rd.term, "") = "" THEN r.read_term
      ELSE rd.term
    END,
    rd.last_mapping_source = r.mapping_source,
    rd.last_mapped_at = datetime()
MERGE (c)-[m:MAPS_TO_READ]->(rd)
SET m.mapping_source = r.mapping_source,
    m.mapping_status = r.mapping_status,
    m.last_seen_at = datetime()
RETURN count(*) AS applied_rows
"""


def _run_dry_batch(session, rows: list[dict]) -> Stats:
    record = session.run(DRY_RUN_QUERY, rows=rows).single()
    return Stats(
        eligible_rows=int(record["eligible_rows"]),
        concept_matches=int(record["concept_matches"]),
        concept_misses=int(record["concept_misses"]),
        read_existing=int(record["read_existing"]),
        read_missing=int(record["read_missing"]),
        rel_existing=int(record["rel_existing"]),
        rel_missing_with_existing_read=int(record["rel_missing_with_existing_read"]),
        rel_needs_new_read=int(record["rel_needs_new_read"]),
    )


def _run_apply_batch(session, rows: list[dict]) -> Stats:
    record = session.run(APPLY_QUERY, rows=rows).single()
    return Stats(applied_rows=int(record["applied_rows"]))


def _print_stats(stats: Stats, mode: str) -> None:
    print(f"Mode: {mode}")
    print(f"Input rows: {stats.input_rows}")
    print(f"Skipped rows: {stats.skipped_rows}")
    print(f"Eligible rows: {stats.eligible_rows}")
    print(f"SNOMED concept matches: {stats.concept_matches}")
    print(f"SNOMED concept misses: {stats.concept_misses}")
    print(f"Existing ReadCode nodes: {stats.read_existing}")
    print(f"Missing ReadCode nodes: {stats.read_missing}")
    print(f"Existing MAPS_TO_READ rels: {stats.rel_existing}")
    print(
        "Missing rels where ReadCode exists: " f"{stats.rel_missing_with_existing_read}"
    )
    print(f"Rels needing ReadCode create: {stats.rel_needs_new_read}")
    if mode == "apply":
        print(f"Rows applied (matched Concept): {stats.applied_rows}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    do_apply = bool(args.apply)
    mode = "apply" if do_apply else "dry-run"

    uri, user, password = _load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    stats = Stats()
    batch: list[dict] = []
    processed = 0

    try:
        with driver.session() as session:
            for rec in _iter_jsonl(args.jsonl):
                stats.input_rows += 1
                row = _to_row(rec)
                if row is None:
                    stats.skipped_rows += 1
                    continue
                batch.append(row)
                if len(batch) >= args.batch_size:
                    chunk_stats = (
                        _run_apply_batch(session, batch)
                        if do_apply
                        else _run_dry_batch(session, batch)
                    )
                    chunk_stats.eligible_rows = len(batch)
                    stats.merge(chunk_stats)
                    processed += len(batch)
                    print(f"Processed {processed} rows...")
                    batch = []
                if args.limit is not None and stats.input_rows >= args.limit:
                    break

            if batch:
                chunk_stats = (
                    _run_apply_batch(session, batch)
                    if do_apply
                    else _run_dry_batch(session, batch)
                )
                chunk_stats.eligible_rows = len(batch)
                stats.merge(chunk_stats)
                processed += len(batch)
                print(f"Processed {processed} rows...")
    finally:
        driver.close()

    _print_stats(stats, mode)


if __name__ == "__main__":
    main()
