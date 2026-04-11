"""Inspect how cancer domain concepts are stored in Neo4j."""

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

QUERIES = [
    (
        "ValueSet labels",
        "MATCH (n:ValueSet) RETURN labels(n) AS lbl, n.id AS id, n.name AS name LIMIT 5",
    ),
    (
        "Node labels with 'breast'",
        "MATCH (n) WHERE any(k IN keys(n) WHERE toLower(toString(n[k])) CONTAINS 'breast') "
        "RETURN labels(n) AS lbl, n.id AS id, n.name AS name, n.milestone_type AS mt LIMIT 10",
    ),
    (
        "Domain nodes",
        "MATCH (n) WHERE 'MilestoneDomain' IN labels(n) OR 'CancerDomain' IN labels(n) "
        "OR 'Domain' IN labels(n) RETURN labels(n) AS lbl, n.id AS id, n.name AS name LIMIT 10",
    ),
    (
        "FHIR ValueSet",
        "MATCH (n:FHIRValueSet) RETURN n.id AS id, n.name AS name LIMIT 10",
    ),
    (
        "All node labels sample",
        "CALL db.labels() YIELD label RETURN label ORDER BY label",
    ),
]


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    for title, q in QUERIES:
        print(f"\n=== {title} ===")
        try:
            rows = client.run(q) or []
            if not rows:
                print("  (no results)")
            for r in rows[:15]:
                print(" ", dict(r))
        except Exception as exc:
            print(f"  ERROR: {exc}")

    client.close()


if __name__ == "__main__":
    main()
