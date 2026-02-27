#!/usr/bin/env python3
"""Neo4j migration: relabel SafetyNetAlert -> SafetyNetAlert, EpisodeOfCare -> EpisodeOfCare.

Run once against each Neo4j instance (Patient Graph) to update existing data.
Idempotent: safe to re-run.

Usage:
    python scripts/migrate_graph_labels.py [--uri bolt://localhost:7687] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS = [
    {
        "description": "Relabel SafetyNetAlert -> SafetyNetAlert",
        "query": """
            MATCH (n:SafetyNetAlert)
            SET n:SafetyNetAlert
            REMOVE n:SafetyNetAlert
            RETURN count(n) AS migrated
        """,
    },
    {
        "description": "Rename HAS_SAFETY_NET_ALERT -> HAS_SAFETY_NET_ALERT relationships",
        "query": """
            MATCH (a)-[r:HAS_SAFETY_NET_ALERT]->(b)
            CREATE (a)-[r2:HAS_SAFETY_NET_ALERT]->(b)
            SET r2 = properties(r)
            DELETE r
            RETURN count(r2) AS migrated
        """,
    },
    {
        "description": "Relabel EpisodeOfCare -> EpisodeOfCare",
        "query": """
            MATCH (n:EpisodeOfCare)
            SET n:EpisodeOfCare
            REMOVE n:EpisodeOfCare
            RETURN count(n) AS migrated
        """,
    },
    {
        "description": "Rename HAS_EPISODE_OF_CARE -> HAS_EPISODE_OF_CARE relationships",
        "query": """
            MATCH (a)-[r:HAS_EPISODE_OF_CARE]->(b)
            CREATE (a)-[r2:HAS_EPISODE_OF_CARE]->(b)
            SET r2 = properties(r)
            DELETE r
            RETURN count(r2) AS migrated
        """,
    },
    {
        "description": "Rename condition_type -> condition_type property on EpisodeOfCare",
        "query": """
            MATCH (n:EpisodeOfCare)
            WHERE n.condition_type IS NOT NULL
            SET n.condition_type = n.condition_type
            REMOVE n.condition_type
            RETURN count(n) AS migrated
        """,
    },
    {
        "description": "Add domain property (default 'oncology') to EpisodeOfCare",
        "query": """
            MATCH (n:EpisodeOfCare)
            WHERE n.domain IS NULL
            SET n.domain = 'oncology'
            RETURN count(n) AS migrated
        """,
    },
    {
        "description": "Create index on SafetyNetAlert(alert_id)",
        "query": "CREATE INDEX IF NOT EXISTS FOR (n:SafetyNetAlert) ON (n.alert_id)",
        "no_return": True,
    },
    {
        "description": "Create index on EpisodeOfCare(episode_id)",
        "query": "CREATE INDEX IF NOT EXISTS FOR (n:EpisodeOfCare) ON (n.episode_id)",
        "no_return": True,
    },
    {
        "description": "Drop old SafetyNetAlert index if exists",
        "query": "DROP INDEX index_SafetyNetAlert_alert_id IF EXISTS",
        "no_return": True,
    },
    {
        "description": "Drop old EpisodeOfCare index if exists",
        "query": "DROP INDEX index_EpisodeOfCare_episode_id IF EXISTS",
        "no_return": True,
    },
]


def run_migrations(uri: str, user: str, password: str, database: str, dry_run: bool = False):
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            for migration in MIGRATIONS:
                desc = migration["description"]
                query = migration["query"]
                if dry_run:
                    logger.info("[DRY RUN] Would execute: %s", desc)
                    continue
                logger.info("Running: %s", desc)
                result = session.run(query)
                if not migration.get("no_return"):
                    record = result.single()
                    count = record["migrated"] if record else 0
                    logger.info("  -> %d nodes/relationships migrated", count)
                else:
                    result.consume()
                    logger.info("  -> done")
    finally:
        driver.close()
    logger.info("Migration complete.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--dry-run", action="store_true", help="Print queries without executing")
    args = parser.parse_args()

    if not args.password and not args.dry_run:
        logger.error("NEO4J_PASSWORD env var or --password required (unless --dry-run)")
        sys.exit(1)

    run_migrations(args.uri, args.user, args.password, args.database, args.dry_run)


if __name__ == "__main__":
    main()
