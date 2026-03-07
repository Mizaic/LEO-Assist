import sys; sys.path.insert(0, ".")
from libs.neo4j_client.client import KnowledgeGraphClient
kg = KnowledgeGraphClient()
rows = kg.run(
    "MATCH (bv:BenchmarkValue) WHERE bv.metric_id CONTAINS 'comorbidity' "
    "RETURN bv.scope_id AS scope, bv.metric_id AS metric, bv.value AS val "
    "ORDER BY bv.metric_id, bv.scope_id"
)
print(f"Comorbidity BenchmarkValue nodes: {len(rows)}")
for r in rows:
    print(f"  {str(r['scope']):15s}  {str(r['metric']):55s}  {r['val']}")
kg.close()
