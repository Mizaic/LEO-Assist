"""Cleanup / reset Cypher queries for the Patient Graph.

Centralised from services/api/app/models/neo4j_schema.py.
"""

RESET_PATIENT_REVIEW_QUEUE = """
MATCH (c:EncounterCandidate {patient_id: $patient_id})
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)
OPTIONAL MATCH (t)-[:HAS_APPROVAL]->(a:Approval)
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
WITH collect(DISTINCT c) AS candidates,
     collect(DISTINCT t) AS tasks,
     collect(DISTINCT a) AS approvals,
     collect(DISTINCT chg) AS changes
WITH [x IN (candidates + tasks + approvals + changes) WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

RESET_ENCOUNTER_REVIEW_QUEUE = """
MATCH (c:EncounterCandidate {patient_id: $patient_id, encounter_id: $encounter_id})
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)
OPTIONAL MATCH (t)-[:HAS_APPROVAL]->(a:Approval)
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
WITH collect(DISTINCT c) AS candidates,
     collect(DISTINCT t) AS tasks,
     collect(DISTINCT a) AS approvals,
     collect(DISTINCT chg) AS changes
WITH [x IN (candidates + tasks + approvals + changes) WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

RESET_PATIENT_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id
WITH count(r) AS links_deleted
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id
DELETE r
RETURN links_deleted
"""

RESET_PATIENT_DIRECT_SEMANTIC = """
MATCH (p:Patient)-[r]->(s)
WHERE toString(p.id) = $patient_id
  AND (s:SnomedConcept OR s:Clinical_finding OR s:Disease OR s:Situation
       OR s:Observable_entity OR s:Procedure)
DELETE r
RETURN count(r) AS direct_deleted
"""

DELETE_ENCOUNTER_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
DELETE r
"""
