"""Check comorbidity benchmark data in ncda_2018_benchmarks.json and Neo4j."""
import sys, json
sys.path.insert(0, ".")

# 1. Check the JSON file structure
with open("external_content/ncda_2018_benchmarks.json") as f:
    data = json.load(f)

print("=== JSON file top-level structure ===")
if isinstance(data, list):
    print(f"  List with {len(data)} items")
    for item in data[:3]:
        print(f"  Item keys: {list(item.keys()) if isinstance(item, dict) else type(item)}")
elif isinstance(data, dict):
    print(f"  Dict with keys: {list(data.keys())[:10]}")

print("\n=== Comorbidity keys in benchmark JSON ===")
def find_comorbidity_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "comorbid" in str(k).lower():
                print(f"  {path}.{k} = {v!r}")
            find_comorbidity_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_comorbidity_keys(item, f"{path}[{i}]")

find_comorbidity_keys(data)

# 2. Check what's in Neo4j BenchmarkSet
print("\n=== BenchmarkSet nodes in Neo4j ===")
from libs.neo4j_client.client import KnowledgeGraphClient
kg = KnowledgeGraphClient()
sets = kg.run("MATCH (bs:BenchmarkSet) RETURN bs.id AS id, bs.ods_code AS ods, bs.scope AS scope, bs.title AS title LIMIT 10")
for r in sets:
    print(f"  id={r['id']}  ods={r['ods']}  scope={r['scope']}  title={r['title']}")

print("\n=== BenchmarkValue nodes with comorbidity keys ===")
vals = kg.run(
    "MATCH (bv:BenchmarkValue) WHERE bv.metric CONTAINS 'comorbidity' "
    "RETURN bv.metric AS metric, bv.value AS val, bv.scope AS scope, bv.ods_code AS ods LIMIT 20"
)
if vals:
    for r in vals:
        print(f"  metric={r['metric']}  value={r['val']}  scope={r['scope']}  ods={r['ods']}")
else:
    print("  None found")

kg.close()
