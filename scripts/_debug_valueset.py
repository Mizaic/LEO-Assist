"""Inspect the ncda-comorbidities ValueSet node and AuditDomain structure."""
import sys, json
sys.path.insert(0, ".")
from libs.neo4j_client.client import KnowledgeGraphClient

kg = KnowledgeGraphClient()

# 1. All properties on the ValueSet node
print("=== ncda-comorbidities ValueSet properties ===")
rows = kg.run("MATCH (v:ValueSet {id: 'ncda-comorbidities'}) RETURN keys(v) AS ks, v AS node")
for r in rows:
    print("  Keys:", r["ks"])
    node = dict(r["node"])
    for k, v in node.items():
        val_preview = str(v)[:120] if v else v
        print(f"  {k}: {val_preview!r}")

# 2. Check AuditDomain nodes
print("\n=== AuditDomain nodes ===")
rows2 = kg.run("MATCH (d:AuditDomain) RETURN d.id AS id, d.name AS name, keys(d) AS ks LIMIT 10")
for r in rows2:
    print(f"  id={r['id']}  name={r['name']}  keys={r['ks']}")

# 3. Check what relationships/children the ValueSet has
print("\n=== ncda-comorbidities relationships ===")
rows3 = kg.run(
    "MATCH (v:ValueSet {id: 'ncda-comorbidities'})-[r]->(n) "
    "RETURN type(r) AS rel, labels(n) AS lbs, n.id AS nid, n.conceptId AS cid, n.display AS disp LIMIT 20"
)
for r in rows3:
    print(f"  -{r['rel']}->  labels={r['lbs']}  id={r['nid']}  conceptId={r['cid']}  display={r['disp']}")

# 4. Check for concept children directly
print("\n=== Children of ncda-comorbidities via HAS_CONCEPT ===")
rows4 = kg.run(
    "MATCH (v:ValueSet {id: 'ncda-comorbidities'})-[:HAS_CONCEPT]->(c) "
    "RETURN c.conceptId AS conceptId, c.display AS display, c.code AS code, keys(c) AS ks LIMIT 20"
)
for r in rows4:
    print(f"  conceptId={r['conceptId']}  display={r['display']}  code={r['code']}  keys={r['ks']}")

kg.close()
