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

from libs.neo4j_client.client import PatientGraphClient


def main() -> None:
    client = PatientGraphClient()

    rows = client.run(
        "MATCH (bs:BenchmarkSet)-[:HAS_VALUE]->(bv:BenchmarkValue) "
        "WHERE bv.metric_id CONTAINS 'cancer_type' "
        "RETURN bs.id AS set_id, bv.metric_id AS metric, bv.value AS val "
        "ORDER BY bs.id, bv.metric_id"
    )
    for r in rows:
        print(f"{str(r['set_id']):<20} {str(r['metric']):<50} {r['val']}")

    print()
    print("--- All BenchmarkSets ---")
    sets = client.run("MATCH (bs:BenchmarkSet) RETURN bs.id AS id, bs.name AS name, bs.audit_year AS year")
    for r in sets:
        print(f"  {r['id']}  ({r['name']}, {r['year']})")

    client.close()


if __name__ == "__main__":
    main()
