"""Cleanup / reset Cypher queries for the Patient Graph.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

Centralised from services/api/app/models/neo4j_schema.py.
"""

# Patient -> SNOMED-ish shortcuts: current pipeline names (documents_queries._REL_BY_LABEL)
# plus legacy types still seen in graphs (e.g. gds_projection_manager).
PATIENT_SEMANTIC_SHORTCUT_REL_TYPES: tuple[str, ...] = (
    "HAS_FINDING",
    "HAS_DISORDER",
    "HAS_DISEASE",
    "HAS_CLINICAL_FINDING",
    "HAS_SITUATION",
    "HAS_OBSERVABLE",
    "HAS_OBSERVABLE_ENTITY",
    "HAS_PROCEDURE",
    "HAS_CONCEPT",
)

_PATIENT_SEMANTIC_SHORTCUT_REL_UNION = "|".join(PATIENT_SEMANTIC_SHORTCUT_REL_TYPES)
_PATIENT_SEMANTIC_SHORTCUT_REL_LIST = ",\n  ".join(
    f"'{name}'" for name in PATIENT_SEMANTIC_SHORTCUT_REL_TYPES
)

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
FOREACH (n IN nodes | DETACH DELETE n)
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
FOREACH (n IN nodes | DETACH DELETE n)
RETURN deleted
"""

# Encounter-[:DOCUMENTS]-> and Chunk-[:DOCUMENTS]-> (sentence-level coding).
RESET_PATIENT_DOCUMENTS = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)-[re:DOCUMENTS]->()
WITH p, collect(re) AS enc_col
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(:DocumentReference)
      -[:HAS_CHUNK]->(:Chunk)-[rc:DOCUMENTS]->()
WITH [r IN enc_col + collect(rc) WHERE r IS NOT NULL] AS rels
WITH rels, size(rels) AS links_deleted
FOREACH (rel IN rels | DELETE rel)
RETURN links_deleted
"""

# Patient-level shortcuts parallel to DOCUMENTS (PATIENT_SEMANTIC_SHORTCUT_REL_TYPES).
RESET_PATIENT_DIRECT_SEMANTIC = f"""
MATCH (p:Patient)-[r:{_PATIENT_SEMANTIC_SHORTCUT_REL_UNION}]->()
WHERE toString(p.id) = $patient_id
WITH collect(r) AS rels
WITH rels, size(rels) AS direct_deleted
FOREACH (rel IN rels | DELETE rel)
RETURN direct_deleted
"""

RESET_PATIENT_LLM_USAGE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)--(u:LLMUsage)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT u) AS nodes
WITH nodes, size(nodes) AS deleted
FOREACH (n IN nodes | DETACH DELETE n)
RETURN deleted
"""

RESET_PATIENT_CODING_DECISIONS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
WITH collect(DISTINCT toString(e.id)) AS enc_ids
UNWIND enc_ids AS eid
MATCH (d:CodingDecision)
WHERE d.decision_id STARTS WITH ('dec:' + eid + ':')
WITH collect(d) AS nodes
WITH nodes, size(nodes) AS deleted
FOREACH (n IN nodes | DETACH DELETE n)
RETURN deleted
"""

RESET_PATIENT_SENTENCES_PAYLOAD = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND e.sentences_payload IS NOT NULL
REMOVE e.sentences_payload
RETURN count(e) AS deleted
"""

RESET_PATIENT_ALERTS = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a1:SafetyNetAlert)
WITH p, collect(DISTINCT a1) AS linked_alerts
OPTIONAL MATCH (a2:SafetyNetAlert)
WHERE toString(a2.patient_id) = toString(p.id)
WITH linked_alerts, collect(DISTINCT a2) AS direct_alerts
WITH linked_alerts + direct_alerts AS raw
UNWIND raw AS n
WITH collect(DISTINCT n) AS nodes
WITH [x IN nodes WHERE x IS NOT NULL] AS clean, size([x IN nodes WHERE x IS NOT NULL]) AS deleted
FOREACH (x IN clean | DETACH DELETE x)
RETURN deleted
"""

RESET_PATIENT_EPISODES = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep1:EpisodeOfCare)
WITH p, collect(DISTINCT ep1) AS linked_episodes
OPTIONAL MATCH (ep2:EpisodeOfCare)
WHERE toString(ep2.patient_id) = toString(p.id)
WITH linked_episodes, collect(DISTINCT ep2) AS direct_episodes
WITH linked_episodes + direct_episodes AS raw
UNWIND raw AS n
WITH collect(DISTINCT n) AS nodes
WITH [x IN nodes WHERE x IS NOT NULL] AS clean, size([x IN nodes WHERE x IS NOT NULL]) AS deleted
FOREACH (x IN clean | DETACH DELETE x)
RETURN deleted
"""

RESET_PATIENT_LEGACY_ALERTS = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_CSS_ALERT]->(a1:CSSAlert)
WITH p, collect(DISTINCT a1) AS linked_alerts
OPTIONAL MATCH (a2:CSSAlert)
WHERE toString(a2.patient_id) = toString(p.id)
WITH linked_alerts, collect(DISTINCT a2) AS direct_alerts
WITH linked_alerts + direct_alerts AS raw
UNWIND raw AS n
WITH collect(DISTINCT n) AS nodes
WITH [x IN nodes WHERE x IS NOT NULL] AS clean, size([x IN nodes WHERE x IS NOT NULL]) AS deleted
FOREACH (x IN clean | DETACH DELETE x)
RETURN deleted
"""

RESET_PATIENT_LEGACY_EPISODES = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_EPISODE]->(ep1:CancerEpisode)
WITH p, collect(DISTINCT ep1) AS linked_episodes
OPTIONAL MATCH (ep2:CancerEpisode)
WHERE toString(ep2.patient_id) = toString(p.id)
WITH linked_episodes, collect(DISTINCT ep2) AS direct_episodes
WITH linked_episodes + direct_episodes AS raw
UNWIND raw AS n
WITH collect(DISTINCT n) AS nodes
WITH [x IN nodes WHERE x IS NOT NULL] AS clean, size([x IN nodes WHERE x IS NOT NULL]) AS deleted
FOREACH (x IN clean | DETACH DELETE x)
RETURN deleted
"""

DELETE_ENCOUNTER_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
WITH collect(r) AS rels
WITH rels, size(rels) AS deleted
FOREACH (rel IN rels | DELETE rel)
RETURN deleted
"""

DELETE_ENCOUNTER_EPISODE_LINKS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:IS_PART_OF]->(:EpisodeOfCare)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
WITH collect(r) AS rels
WITH rels, size(rels) AS deleted
FOREACH (rel IN rels | DELETE rel)
RETURN deleted
"""

LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(s)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
RETURN collect(DISTINCT toString(s.conceptId)) AS concept_ids
"""

CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS = f"""
UNWIND $concept_ids AS cid
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (s)
WHERE toString(s.conceptId) = cid
WITH DISTINCT p, s, cid
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e2:Encounter)-[r2:DOCUMENTS]->(s)
WITH p, s, cid, count(r2) AS remaining_docs
WHERE remaining_docs = 0
OPTIONAL MATCH (p)-[pr]->(s)
WHERE type(pr) IN [
  {_PATIENT_SEMANTIC_SHORTCUT_REL_LIST}
]
WITH cid, collect(pr) AS rels
UNWIND rels AS rel
DELETE rel
RETURN count(rel) AS shortcuts_deleted
"""

DELETE_ORPHAN_ENCOUNTER_LLM_USAGE = """
MATCH (e:Encounter)
WHERE toString(e.id) = $encounter_id
OPTIONAL MATCH (e)--(u:LLMUsage)
WITH e, collect(DISTINCT u) AS usages
UNWIND usages AS u
WITH e, u
WHERE u IS NOT NULL
OPTIONAL MATCH (u)--(other:Encounter)
WHERE other <> e
WITH u, count(other) AS other_encounters
WHERE other_encounters = 0
WITH collect(u) AS to_delete
WITH to_delete, size(to_delete) AS llm_usage_deleted
FOREACH (x IN to_delete | DETACH DELETE x)
RETURN llm_usage_deleted
"""

DELETE_ENCOUNTER_CODING_DECISIONS = """
MATCH (d:CodingDecision)
WHERE toString(d.decision_id) STARTS WITH $decision_prefix
WITH collect(d) AS nodes
WITH nodes, size(nodes) AS decisions_deleted
FOREACH (n IN nodes | DETACH DELETE n)
RETURN decisions_deleted
"""

CLEAR_ENCOUNTER_SENTENCES_PAYLOAD = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
REMOVE e.sentences_payload
RETURN count(e) AS encounters_cleared
"""
