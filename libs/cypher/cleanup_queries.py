"""Cleanup / reset Cypher queries for the Patient Graph.

Centralised from services/api/app/models/neo4j_schema.py.
"""

RESET_PATIENT_REVIEW_QUEUE = """
MATCH (c:EncounterCandidate)
WHERE toString(c.patient_id) = $patient_id
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
MATCH (c:EncounterCandidate)
WHERE toString(c.patient_id) = $patient_id
  AND toString(c.encounter_id) = $encounter_id
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

RESET_PATIENT_ALERTS = """
MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT a) AS linked_alerts
MATCH (a:SafetyNetAlert)
WHERE toString(a.patient_id) = $patient_id
WITH linked_alerts, collect(DISTINCT a) AS direct_alerts
WITH linked_alerts + direct_alerts AS alerts
WITH [x IN alerts WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

RESET_PATIENT_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT ep) AS linked_episodes
MATCH (ep:EpisodeOfCare)
WHERE toString(ep.patient_id) = $patient_id
WITH linked_episodes, collect(DISTINCT ep) AS direct_episodes
WITH linked_episodes + direct_episodes AS episodes
WITH [x IN episodes WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

RESET_PATIENT_LEGACY_ALERTS = """
MATCH (p:Patient)-[:HAS_CSS_ALERT]->(a:CSSAlert)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT a) AS linked_alerts
MATCH (a:CSSAlert)
WHERE toString(a.patient_id) = $patient_id
WITH linked_alerts, collect(DISTINCT a) AS direct_alerts
WITH linked_alerts + direct_alerts AS alerts
WITH [x IN alerts WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

RESET_PATIENT_LEGACY_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT ep) AS linked_episodes
MATCH (ep:CancerEpisode)
WHERE toString(ep.patient_id) = $patient_id
WITH linked_episodes, collect(DISTINCT ep) AS direct_episodes
WITH linked_episodes + direct_episodes AS episodes
WITH [x IN episodes WHERE x IS NOT NULL | x] AS nodes
WITH nodes, size(nodes) AS deleted
UNWIND nodes AS n
DETACH DELETE n
RETURN deleted
"""

DELETE_ENCOUNTER_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
DELETE r
"""
