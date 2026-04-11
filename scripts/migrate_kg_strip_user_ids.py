"""Remove user identifier fields from SurfaceForm and MAPS_TO in KG."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env", override=False)

STRIP_SF = """
MATCH (sf:SurfaceForm)
REMOVE sf.created_by, sf.approved_by
RETURN count(sf) AS updated
"""

STRIP_RELS = """
MATCH (:SurfaceForm)-[m:MAPS_TO]->(:Concept)
REMOVE m.created_by, m.approved_by
RETURN count(m) AS updated
"""


def main() -> None:
    uri = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password")
    )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        sf = session.run(STRIP_SF).single()
        rels = session.run(STRIP_RELS).single()
    driver.close()
    print(
        f"surface_forms_updated={sf['updated'] if sf else 0} rels_updated={rels['updated'] if rels else 0}"
    )


if __name__ == "__main__":
    main()
