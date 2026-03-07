"""Check entities in benchmark JSON and what the loader produces for comorbidities."""
import sys, json
sys.path.insert(0, ".")

with open("external_content/ncda_2018_benchmarks.json") as f:
    data = json.load(f)

print("=== Entities in JSON ===")
for e in data.get("entities", []):
    print(f"  {e}")

print("\n=== What flatten_benchmarks produces for demographics ===")
from services.fhir_api.app.services.benchmark_loader import flatten_benchmarks
records = flatten_benchmarks(data, template_id="ncda")
print(f"  Total records: {len(records)}")

# Show comorbidity records
comorb = [r for r in records if "comorbid" in r.get("metric_id", "")]
print(f"\n=== Comorbidity records ({len(comorb)}) ===")
for r in comorb:
    print(f"  scope_id={r['scope_id']!r}  metric_id={r['metric_id']!r}  value={r['value']}")

# Check what Neo4j has vs what the loader produces
print("\n=== All BenchmarkValue metrics in Neo4j ===")
from libs.neo4j_client.client import KnowledgeGraphClient
kg = KnowledgeGraphClient()
rows = kg.run(
    "MATCH (bv:BenchmarkValue) "
    "RETURN DISTINCT bv.metric_id AS mid, bv.category AS cat, count(*) AS n ORDER BY cat, mid LIMIT 50"
)
for r in rows:
    print(f"  {r['cat']}.{r['mid']}  ({r['n']} scopes)")

kg.close()
