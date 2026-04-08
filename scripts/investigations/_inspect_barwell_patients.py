"""Inspect the 2 patients linked to C82061 (Barwell & Hollycroft) before any fix."""
from libs.neo4j_client.client import PatientGraphClient

c = PatientGraphClient()

print("=== Patients linked to C82061 ===")
rows = c.run(
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization {id: 'C82061'}) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN p.id AS patient_id, "
    "       collect(DISTINCT ep.episode_id) AS episode_ids, "
    "       collect(DISTINCT ep.cancer_type) AS cancer_types, "
    "       collect(DISTINCT ep.status) AS statuses"
)
for r in rows:
    print(r)

print()
print("=== Confirm C82070 (Woodbrook) exists ===")
rows2 = c.run(
    "MATCH (o:Organization {id: 'C82070'}) "
    "RETURN o.id AS id, o.name AS name"
)
for r in rows2:
    print(r)

c.close()
