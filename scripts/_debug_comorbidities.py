"""Diagnostic: check HAS_DISEASE types and ValueSet concept IDs."""
import sys, json
sys.path.insert(0, ".")
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient

pg = PatientGraphClient()

# 1. Check HAS_DISEASE after migration
rows = pg.run(
    "MATCH (p:Patient)-[r:HAS_DISEASE]->(d) "
    "WHERE r.domain = 'comorbidities' "
    "RETURN d.conceptId AS cid, r.benchmark_key AS bm_key LIMIT 10"
)
print("=== HAS_DISEASE sample (after migration) ===")
for r in rows:
    print(f"  conceptId={r['cid']!r}  type={type(r['cid']).__name__}  bm_key={r['bm_key']}")

pg.close()

# 2. Check ValueSet concept codes
kg = KnowledgeGraphClient()
vs_rows = kg.run(
    "MATCH (v:ValueSet) WHERE v.id = 'ncda-comorbidities' "
    "RETURN v.rawJson LIMIT 1"
)
print("\n=== ncda-comorbidities ValueSet concepts ===")
if vs_rows and vs_rows[0].get("rawJson"):
    raw = vs_rows[0]["rawJson"]
    vs = json.loads(raw) if isinstance(raw, str) else raw
    for inc in (vs.get("compose") or {}).get("include") or []:
        for c in inc.get("concept") or []:
            code = c.get("code")
            print(f"  code={code!r}  type={type(code).__name__}  display={c.get('display')}")
else:
    print("  No ncda-comorbidities ValueSet found in KG")

kg.close()
