"""Backfill `:Term.embedding` vectors in Neo4j.

This script embeds `Term.surface_form` text and writes vectors to Neo4j for
hybrid retrieval. Use `--dry-run` first to inspect workload.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from embedding_utils import TextEmbedder, load_vector_settings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = 512

FETCH_QUERY = """
MATCH (t:Term)
WHERE t.surface_form IS NOT NULL
  AND ($overwrite OR t.embedding IS NULL)
RETURN t.id AS id, t.surface_form AS text
ORDER BY t.id
LIMIT $limit
"""

UPSERT_QUERY = """
UNWIND $rows AS r
MATCH (t:Term {id: r.id})
SET t.embedding = r.embedding,
    t.embedding_model = $model_name,
    t.embedding_dim = $dim,
    t.embedding_updated_at = datetime()
"""


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("CODING_GRAPH_NEO4J_URI", "").strip()
    user = os.environ.get("CODING_GRAPH_NEO4J_USERNAME", "").strip()
    password = os.environ.get("CODING_GRAPH_NEO4J_PASSWORD", "").strip()
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in secrets/.env")
    return uri, user, password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25_000)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vector = load_vector_settings()
    uri, user, password = load_neo4j_config()

    driver = GraphDatabase.driver(uri, auth=(user, password))
    embedder = TextEmbedder(vector)

    total = 0
    batches = 0
    try:
        with driver.session() as session:
            records = list(
                session.run(
                    FETCH_QUERY, overwrite=args.overwrite, limit=args.limit
                )
            )
            if not records:
                print("No terms to embed.")
                return

            print(f"Terms queued: {len(records)}")
            if args.dry_run:
                print("Dry run only. No writes performed.")
                print(f"Model: {vector.model_name}")
                print(f"Expected dimension: {vector.dimension}")
                print("Sample terms:")
                for rec in records[:10]:
                    print(f"- {rec['id']}: {rec['text']}")
                return

            for i in range(0, len(records), args.batch_size):
                chunk = records[i : i + args.batch_size]
                texts = [str(r["text"]) for r in chunk]
                ids = [str(r["id"]) for r in chunk]
                vectors = embedder.encode(texts)

                rows = []
                for term_id, vec in zip(ids, vectors, strict=True):
                    if len(vec) != vector.dimension:
                        raise RuntimeError(
                            f"Embedding dimension mismatch for {term_id}: "
                            f"{len(vec)} != {vector.dimension}"
                        )
                    rows.append({"id": term_id, "embedding": vec})

                session.run(
                    UPSERT_QUERY,
                    rows=rows,
                    model_name=vector.model_name,
                    dim=vector.dimension,
                )

                total += len(rows)
                batches += 1
                print(f"Embedded {total} terms across {batches} batches...")
    finally:
        driver.close()

    print("Embedding backfill complete.")
    print(f"Model: {vector.model_name}")
    print(f"Terms embedded: {total}")


if __name__ == "__main__":
    main()
