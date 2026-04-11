"""Read all cancer_type benchmark values from the KG."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient


def main() -> None:
    client = KnowledgeGraphClient()

    rows = client.run(
        "MATCH (bv:BenchmarkValue) "
        "WHERE bv.audit_id = 'ncda-2018' AND bv.category = 'condition_type' "
        "RETURN bv.metric_id AS metric, bv.scope_type AS scope, bv.value AS val "
        "ORDER BY bv.metric_id, bv.scope_type"
    )
    print(f"{'Metric':<45} {'Scope':<20} {'Value'}")
    print("-" * 70)
    for r in rows:
        print(f"{str(r['metric']):<45} {str(r['scope']):<20} {r['val']}")

    print()
    print("--- All BenchmarkSets ---")
    sets = client.run(
        "MATCH (bs:BenchmarkSet) RETURN bs.id AS id, bs.name AS name, bs.audit_year AS year"
    )
    for r in sets:
        print(f"  {r['id']}  ({r['name']}, {r['year']})")

    client.close()


if __name__ == "__main__":
    main()
