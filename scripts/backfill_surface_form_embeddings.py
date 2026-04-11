"""Backfill `:SurfaceForm.embedding` vectors in Neo4j.

Embeds surface forms that come from the writeback flows used by operations UI:
- manual mapping corrections (`source=manual`)
- coding review resolves (`source=coding_review`)
- LLM-assisted recheck writeback (`source=coding_review_recheck`)
- HITL approved writeback sync (`source=hitl_approved`)

This script writes embeddings and ensures the `surface_form_embedding_idx`
vector index exists.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from embedding_utils import TextEmbedder, load_vector_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

os.environ.setdefault("SENTENCE_TRANSFORMERS_VERBOSITY", "warning")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "warning")

log = logging.getLogger("backfill_surface_embeddings")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = 512
DEFAULT_SOURCES = "manual,coding_review,coding_review_recheck,hitl_approved"

COUNT_QUERY = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND coalesce(sf.status, 'active') = 'active'
  AND ($include_all_sources OR coalesce(sf.source, 'manual') IN $sources)
  AND ($overwrite OR sf.embedding IS NULL)
RETURN count(DISTINCT sf) AS total
"""

FETCH_QUERY = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND coalesce(sf.status, 'active') = 'active'
  AND ($include_all_sources OR coalesce(sf.source, 'manual') IN $sources)
  AND ($overwrite OR sf.embedding IS NULL)
WITH DISTINCT sf
RETURN sf.normalized AS normalized,
       coalesce(sf.form, sf.normalized) AS text,
       coalesce(sf.source, 'manual') AS source,
       coalesce(sf.created_by, 'unknown') AS created_by
ORDER BY sf.normalized
LIMIT $page_size
"""

DUPLICATE_REL_AUDIT_QUERY = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WHERE c.active = true
  AND coalesce(sf.status, 'active') = 'active'
WITH sf, count(r) AS rels
WHERE rels > 1
RETURN count(sf) AS surface_forms_with_duplicate_rels
"""

UPSERT_QUERY = """
UNWIND $rows AS r
MATCH (sf:SurfaceForm {normalized: r.normalized})
SET sf.embedding = r.embedding,
    sf.embedding_model = $model_name,
    sf.embedding_dim = $dim,
    sf.embedding_updated_at = datetime()
"""


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "").strip()
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "").strip()
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "").strip()
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in secrets/.env")
    return uri, user, password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max total surface forms to embed (0 = no limit)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH,
        help="Embedding batch size",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=10_000,
        help="Surface forms fetched from Neo4j per round-trip",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--sources",
        type=str,
        default=DEFAULT_SOURCES,
        help="Comma-separated source values to include",
    )
    parser.add_argument(
        "--include-all-sources",
        action="store_true",
        help="Ignore --sources filter and embed all active surface forms",
    )
    return parser.parse_args()


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    mins, secs = divmod(int(seconds), 60)
    if mins < 60:
        return f"{mins}m {secs}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m {secs}s"


def _ensure_vector_index(uri: str, user: str, password: str, dimension: int) -> None:
    index_name = "surface_form_embedding_idx"
    stmt = (
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
        "FOR (sf:SurfaceForm) ON (sf.embedding) "
        "OPTIONS {indexConfig: {"
        f"`vector.dimensions`: {dimension}, "
        "`vector.similarity_function`: 'cosine'"
        "}}"
    )
    log.info("Ensuring vector index '%s' exists...", index_name)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(stmt)
            result = session.run("SHOW INDEXES WHERE name = $name", name=index_name)
            idx = result.single()
            if idx:
                log.info(
                    "Vector index '%s' is %s (type=%s)",
                    index_name,
                    idx.get("state", "?"),
                    idx.get("type", "?"),
                )
            else:
                log.warning(
                    "Vector index '%s' was not found after creation", index_name
                )
    finally:
        driver.close()


def main() -> None:
    args = parse_args()
    vector = load_vector_settings()
    uri, user, password = load_neo4j_config()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    log.info("Model:      %s", vector.model_name)
    log.info("Dimension:  %d", vector.dimension)
    log.info("Device:     %s", vector.device)
    log.info("Batch size: %d", args.batch_size)
    log.info("Page size:  %d", args.page_size)
    log.info("Limit:      %s", args.limit if args.limit else "none")
    log.info("Overwrite:  %s", args.overwrite)
    log.info("Sources:    %s", "ALL" if args.include_all_sources else ",".join(sources))

    driver = GraphDatabase.driver(uri, auth=(user, password))
    embedder = TextEmbedder(vector)

    total = 0
    batches = 0
    pages = 0
    run_start = time.time()
    try:
        with driver.session() as session:
            log.info("Counting surface forms to embed...")
            count_result = session.run(
                COUNT_QUERY,
                overwrite=args.overwrite,
                include_all_sources=args.include_all_sources,
                sources=sources,
            )
            grand_total: int = count_result.single()["total"]
            dup_row = session.run(DUPLICATE_REL_AUDIT_QUERY).single()
            dup_count = (
                int(dup_row["surface_forms_with_duplicate_rels"]) if dup_row else 0
            )
            if dup_count > 0:
                log.warning(
                    "Detected %d SurfaceForm nodes with duplicate MAPS_TO links. "
                    "Fetch de-duplicates rows, but run deduplication to clean data.",
                    dup_count,
                )
            if args.limit:
                grand_total = min(grand_total, args.limit)
            log.info("Surface forms remaining: %d", grand_total)

            if args.dry_run:
                log.info("DRY RUN - fetching first page to inspect...")
                records = list(
                    session.run(
                        FETCH_QUERY,
                        overwrite=args.overwrite,
                        include_all_sources=args.include_all_sources,
                        sources=sources,
                        page_size=min(args.page_size, args.limit or args.page_size),
                    )
                )
                log.info("Model: %s", vector.model_name)
                log.info("Expected dimension: %d", vector.dimension)
                for rec in records[:10]:
                    log.info(
                        "  normalized=%s source=%s text=%r",
                        rec["normalized"],
                        rec["source"],
                        rec["text"],
                    )
                return

            if grand_total == 0:
                log.info("No surface forms to embed - all up to date")
                return

            while True:
                remaining_budget = args.limit - total if args.limit else args.page_size
                if args.limit and remaining_budget <= 0:
                    break

                page_size = (
                    min(args.page_size, remaining_budget)
                    if args.limit
                    else args.page_size
                )

                fetch_start = time.time()
                records = list(
                    session.run(
                        FETCH_QUERY,
                        overwrite=args.overwrite,
                        include_all_sources=args.include_all_sources,
                        sources=sources,
                        page_size=page_size,
                    )
                )
                fetch_elapsed = time.time() - fetch_start
                pages += 1

                if not records:
                    break

                log.info(
                    "Page %d: fetched %d surface forms in %.1fs",
                    pages,
                    len(records),
                    fetch_elapsed,
                )

                for i in range(0, len(records), args.batch_size):
                    chunk = records[i : i + args.batch_size]
                    texts = [str(r["text"]) for r in chunk]
                    normalized_keys = [str(r["normalized"]) for r in chunk]

                    embed_start = time.time()
                    vectors = embedder.encode(texts)
                    embed_elapsed = time.time() - embed_start

                    rows = []
                    for normalized, vec in zip(normalized_keys, vectors, strict=True):
                        if len(vec) != vector.dimension:
                            raise RuntimeError(
                                f"Embedding dimension mismatch for {normalized}: "
                                f"{len(vec)} != {vector.dimension}"
                            )
                        rows.append({"normalized": normalized, "embedding": vec})

                    write_start = time.time()
                    session.run(
                        UPSERT_QUERY,
                        rows=rows,
                        model_name=vector.model_name,
                        dim=vector.dimension,
                    )
                    write_elapsed = time.time() - write_start

                    total += len(rows)
                    batches += 1
                    overall_elapsed = time.time() - run_start
                    rate = total / overall_elapsed if overall_elapsed > 0 else 0
                    eta_secs = (grand_total - total) / rate if rate > 0 else 0

                    log.info(
                        "Batch %d  |  %d/%d forms  |  "
                        "embed %.1fs  write %.1fs  |  %.0f forms/s  |  ETA %s",
                        batches,
                        total,
                        grand_total,
                        embed_elapsed,
                        write_elapsed,
                        rate,
                        _fmt_duration(eta_secs),
                    )
    finally:
        driver.close()

    total_elapsed = time.time() - run_start
    if total > 0:
        log.info("Surface form embedding backfill complete")
        log.info("  Forms embedded: %d", total)
        log.info("  Pages fetched:  %d", pages)
        log.info("  Total time:     %s", _fmt_duration(total_elapsed))
        log.info(
            "  Avg rate:       %.0f forms/s",
            total / total_elapsed if total_elapsed > 0 else 0,
        )
        log.info("  Model:          %s", vector.model_name)
        log.info("  Device:         %s", vector.device)

    if total > 0:
        _ensure_vector_index(uri, user, password, vector.dimension)


if __name__ == "__main__":
    main()
