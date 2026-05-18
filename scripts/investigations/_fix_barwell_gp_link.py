"""Fix: re-link patient 9990010053 from C82061 (Barwell) to C82070 (Woodbrook).

This patient was erroneously registered at Barwell & Hollycroft.
All episodes belong to the Woodbrook cohort.

Steps:
  1. Delete HAS_GENERAL_PRACTITIONER -> C82061
  2. Create  HAS_GENERAL_PRACTITIONER -> C82070
  3. Verify the fix
"""

from libs.neo4j_client.client import PatientGraphClient

PATIENT_ID = "9990010053"
OLD_GP = "C82061"
NEW_GP = "C82070"

c = PatientGraphClient()

print(f"--- Before fix: GP links for patient {PATIENT_ID} ---")
before = c.run(
    "MATCH (p:Patient {id: $pid})-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "RETURN gp.id AS gp_id, gp.name AS gp_name",
    pid=PATIENT_ID,
)
for r in before:
    print(r)

print()
print(f"--- Removing link to {OLD_GP} ---")
c.run(
    "MATCH (p:Patient {id: $pid})-[r:HAS_GENERAL_PRACTITIONER]->(gp:Organization {id: $old_gp}) "
    "DELETE r",
    pid=PATIENT_ID,
    old_gp=OLD_GP,
)
print("Deleted.")

print(f"--- Creating link to {NEW_GP} ---")
c.run(
    "MATCH (p:Patient {id: $pid}), (gp:Organization {id: $new_gp}) "
    "MERGE (p)-[:HAS_GENERAL_PRACTITIONER]->(gp)",
    pid=PATIENT_ID,
    new_gp=NEW_GP,
)
print("Created.")

print()
print(f"--- After fix: GP links for patient {PATIENT_ID} ---")
after = c.run(
    "MATCH (p:Patient {id: $pid})-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "RETURN gp.id AS gp_id, gp.name AS gp_name",
    pid=PATIENT_ID,
)
for r in after:
    print(r)

print()
print("--- Final episode counts by practice ---")
counts = c.run(
    "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "RETURN gp.id AS gp_id, gp.name AS gp_name, count(DISTINCT ep) AS episode_count "
    "ORDER BY episode_count DESC"
)
for r in counts:
    print(r)

c.close()
print()
print("Done.")
