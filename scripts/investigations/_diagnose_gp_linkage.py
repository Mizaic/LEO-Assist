"""Diagnostic: find episodes with no HAS_GENERAL_PRACTITIONER link.

Run with:
    python scripts/investigations/_diagnose_gp_linkage.py
"""
from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()

print("=== Unlinked episodes (no HAS_GENERAL_PRACTITIONER) ===")
rows = client.run(
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT (p)-[:HAS_GENERAL_PRACTITIONER]->() "
    "  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN "
    "  count(DISTINCT ep)  AS unlinked_episodes, "
    "  count(DISTINCT p)   AS unlinked_patients, "
    "  collect(DISTINCT ep.cancer_type)[..15] AS sample_cancer_types, "
    "  collect(DISTINCT ep.status)[..10] AS sample_statuses"
)
for r in rows:
    print(r)

print()
print("=== England scope total (no org filter) ===")
rows2 = client.run(
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN count(DISTINCT ep) AS total_england"
)
for r in rows2:
    print(r)

print()
print("=== Practice scope total (requires GP link) ===")
rows3 = client.run(
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN count(DISTINCT ep) AS total_practice, gp.id AS gp_id "
    "ORDER BY total_practice DESC"
)
for r in rows3:
    print(r)

print()
print("=== Unlinked patient IDs (for remediation) ===")
rows4 = client.run(
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT (p)-[:HAS_GENERAL_PRACTITIONER]->() "
    "  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN DISTINCT p.id AS patient_id, "
    "       collect(DISTINCT ep.cancer_type) AS cancer_types, "
    "       collect(DISTINCT ep.status) AS statuses "
    "ORDER BY patient_id"
)
for r in rows4:
    print(r)

client.close()
