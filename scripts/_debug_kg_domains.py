"""Check how domain config is stored in the Knowledge Graph."""
import sys, json
sys.path.insert(0, ".")
from libs.neo4j_client.client import KnowledgeGraphClient

kg = KnowledgeGraphClient()

# 1. What node types exist?
rows = kg.run("MATCH (n) RETURN DISTINCT labels(n) AS lbs LIMIT 30")
print("=== All node labels in KG ===")
for r in rows:
    print(" ", r["lbs"])

# 2. Find anything that looks like a domain config
print("\n=== Nodes with domain-like ids ===")
rows2 = kg.run("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id, labels(n) AS lbs LIMIT 30")
for r in rows2:
    print(f"  id={r['n.id']}  labels={r['lbs']}")

# 3. Find comorbidities specifically
print("\n=== Nodes matching 'comorbidities' ===")
rows3 = kg.run(
    "MATCH (n) WHERE n.id CONTAINS 'comorbidities' OR n.name CONTAINS 'comorbidities' "
    "RETURN n.id, n.name, labels(n) AS lbs LIMIT 10"
)
for r in rows3:
    print(f"  id={r['n.id']}  name={r['n.name']}  labels={r['lbs']}")

kg.close()
