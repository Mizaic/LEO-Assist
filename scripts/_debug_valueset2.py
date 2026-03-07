"""Print the full concept list from ncda-comorbidities and compare to HAS_DISEASE data."""
import sys, json
sys.path.insert(0, ".")
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

kg = KnowledgeGraphClient()

print("=== Concepts in ncda-comorbidities ValueSet ===")
rows = kg.run("MATCH (v:ValueSet {id: 'ncda-comorbidities'}) RETURN v.rawJson AS raw")
if rows and rows[0].get("raw"):
    raw = rows[0]["raw"]
    vs = json.loads(raw) if isinstance(raw, str) else raw
    for inc in (vs.get("compose") or {}).get("include") or []:
        for c in inc.get("concept") or []:
            code = c.get("code")
            display = c.get("display")
            bm_key = next(
                (d.get("value") for d in (c.get("designation") or [])
                 if (d.get("use") or {}).get("code") == "benchmark_key"),
                None
            )
            print(f"  code={code!r}  type={type(code).__name__}  display={display!r}  benchmark_key={bm_key!r}")
else:
    print("  Not found or empty rawJson")

kg.close()

print("\n=== Distinct HAS_DISEASE conceptIds in patient graph ===")
pg = PatientGraphClient()
rows2 = pg.run(
    "MATCH (p:Patient)-[r:HAS_DISEASE]->(d) "
    "WHERE r.domain = 'comorbidities' "
    "RETURN DISTINCT d.conceptId AS cid, count(DISTINCT p) AS n ORDER BY n DESC"
)
for r in rows2:
    print(f"  conceptId={r['cid']!r}  type={type(r['cid']).__name__}  patients={r['n']}")
pg.close()
