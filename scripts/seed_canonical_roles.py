"""Seed the four canonical Wave D roles in Neo4j.

Idempotent: re-running the script against a database that already has the
roles is a no-op. See DI-LEO-AI-129 and VT-LEO-AI-125 TC-004.

Usage:
    python -m scripts.seed_canonical_roles
"""

from __future__ import annotations

import logging
import sys

from libs.cypher.role_queries import CANONICAL_ROLES, SEED_CANONICAL_ROLES
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


def seed(client: PatientGraphClient | None = None) -> list[str]:
    """Seed canonical roles; return the list of role names now present."""
    own = client is None
    graph = client or PatientGraphClient()
    try:
        rows = graph.run(
            SEED_CANONICAL_ROLES,
            role_names=list(CANONICAL_ROLES),
        )
        return [r.get("name") for r in rows if r.get("name")]
    finally:
        if own:
            graph.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    names = seed()
    logger.info("seeded %d canonical role(s): %s", len(names), ",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
