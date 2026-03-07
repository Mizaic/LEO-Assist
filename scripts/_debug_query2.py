"""Verify the referral_date NULL issue."""
import sys
sys.path.insert(0, ".")
from libs.neo4j_client.client import PatientGraphClient

pg = PatientGraphClient()
params = {"org": "C82070"}
base = (
    "MATCH (_scope:Organization {id: $org}) "
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
)

# Check referral_date nulls
print("=== Episodes with/without referral_date ===")
rows = pg.run(
    f"{base}"
    "RETURN count(CASE WHEN ep.referral_date IS NULL THEN 1 END) AS null_ref, "
    "       count(CASE WHEN ep.referral_date IS NOT NULL THEN 1 END) AS has_ref",
    **params
)
for r in rows:
    print(f"  null referral_date: {r['null_ref']}  has referral_date: {r['has_ref']}")

# Check HAS_DISEASE hits WITHOUT the date filter
print("\n=== HAS_DISEASE matches WITHOUT date filter ===")
rows2 = pg.run(
    f"{base}"
    "WITH p, ep "
    "MATCH (p)-[r1:HAS_DISEASE]->(d1) "
    "WHERE r1.domain = 'comorbidities' "
    "RETURN d1.conceptId AS cid, count(DISTINCT p) AS n LIMIT 10",
    **params
)
for r in rows2:
    print(f"  cid={r['cid']!r}  patients={r['n']}")

# Check HAS_DISEASE hits WITH the date filter (the buggy one)
print("\n=== HAS_DISEASE matches WITH date filter (r1.encounter_date <= ep.referral_date) ===")
rows3 = pg.run(
    f"{base}"
    "WITH p, ep "
    "MATCH (p)-[r1:HAS_DISEASE]->(d1) "
    "WHERE r1.domain = 'comorbidities' "
    "  AND (r1.encounter_date IS NULL OR r1.encounter_date <= ep.referral_date) "
    "RETURN d1.conceptId AS cid, count(DISTINCT p) AS n LIMIT 10",
    **params
)
print(f"  Rows: {len(rows3)}")
for r in rows3:
    print(f"  cid={r['cid']!r}  patients={r['n']}")

# Check WITH null-safe date filter (the fix)
print("\n=== HAS_DISEASE WITH null-safe date filter ===")
rows4 = pg.run(
    f"{base}"
    "WITH p, ep "
    "MATCH (p)-[r1:HAS_DISEASE]->(d1) "
    "WHERE r1.domain = 'comorbidities' "
    "  AND (r1.encounter_date IS NULL OR ep.referral_date IS NULL OR r1.encounter_date <= ep.referral_date) "
    "RETURN d1.conceptId AS cid, count(DISTINCT p) AS n ORDER BY n DESC LIMIT 10",
    **params
)
print(f"  Rows: {len(rows4)}")
for r in rows4:
    print(f"  cid={r['cid']!r}  patients={r['n']}")

pg.close()
