"""Neo4j schema and write/query templates for HITL MVP."""

from __future__ import annotations

SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT encounter_candidate_id IF NOT EXISTS FOR (c:EncounterCandidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE CONSTRAINT review_task_id IF NOT EXISTS FOR (t:ReviewTask) REQUIRE t.task_id IS UNIQUE",
    "CREATE CONSTRAINT approval_id IF NOT EXISTS FOR (a:Approval) REQUIRE a.approval_id IS UNIQUE",
    "CREATE CONSTRAINT change_id IF NOT EXISTS FOR (chg:Change) REQUIRE chg.change_id IS UNIQUE",
    "CREATE INDEX review_task_status IF NOT EXISTS FOR (t:ReviewTask) ON (t.status)",
    "CREATE INDEX review_task_priority IF NOT EXISTS FOR (t:ReviewTask) ON (t.priority)",
]


UPSERT_CANDIDATE = """
MERGE (c:EncounterCandidate {candidate_id: $candidate_id})
SET c.patient_id = $patient_id,
    c.encounter_id = $encounter_id,
    c.date = $date,
    c.source_hash = $source_hash,
    c.deidentified_hash = $deidentified_hash,
    c.deidentified_text = $deidentified_text,
    c.approval_status = $approval_status,
    c.hard_fail_reasons = $hard_fail_reasons,
    c.warning_reasons = $warning_reasons,
    c.sentences_json = $sentences_json,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime())
"""


CREATE_REVIEW_TASK = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
MERGE (t:ReviewTask {task_id: $task_id})
SET t.priority = $priority,
    t.status = $status,
    t.assigned_reviewer = $assigned_reviewer,
    t.warning_count = $warning_count,
    t.created_at = coalesce(t.created_at, datetime()),
    t.updated_at = datetime()
MERGE (c)-[:HAS_TASK]->(t)
"""


APPEND_CHANGE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
CREATE (chg:Change {
    change_id: $change_id,
    event_type: $event_type,
    actor: $actor,
    reason: $reason,
    timestamp: datetime($timestamp),
    before_hash: $before_hash,
    after_hash: $after_hash,
    version_bundle_json: $version_bundle_json
})
CREATE (c)-[:HAS_CHANGE]->(chg)
"""


APPEND_APPROVAL = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
CREATE (a:Approval {
    approval_id: $approval_id,
    action: $action,
    reviewer: $reviewer,
    reason: $reason,
    status_after: $status_after,
    timestamp: datetime($timestamp),
    before_hash: $before_hash,
    after_hash: $after_hash
})
CREATE (t)-[:HAS_APPROVAL]->(a)
SET t.status = $status_after, t.updated_at = datetime(), c.approval_status = $status_after
"""


LIST_TASKS = """
MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask)
WHERE ($status IS NULL OR t.status = $status)
  AND ($patient_id IS NULL OR c.patient_id = $patient_id)
WITH c, t
ORDER BY
    CASE WHEN t.status = 'pending' THEN 0 ELSE 1 END ASC,
    t.updated_at DESC
WITH c.patient_id AS patient_id, c.encounter_id AS encounter_id, collect({c: c, t: t})[0] AS latest
WITH latest.c AS c, latest.t AS t
RETURN t.task_id AS task_id,
       c.candidate_id AS candidate_id,
       c.patient_id AS patient_id,
       c.encounter_id AS encounter_id,
       t.priority AS priority,
       t.status AS status,
       t.warning_count AS warning_count,
       t.created_at AS created_at,
       t.updated_at AS updated_at
ORDER BY t.priority DESC, t.updated_at ASC
LIMIT $limit
"""


GET_TASK_DETAIL = """
MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
RETURN t.task_id AS task_id,
       c.candidate_id AS candidate_id,
       c.patient_id AS patient_id,
       c.encounter_id AS encounter_id,
       t.priority AS priority,
       t.status AS status,
       t.warning_count AS warning_count,
       t.created_at AS created_at,
       t.updated_at AS updated_at,
       c AS candidate
"""


GET_AUDIT_TIMELINE = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c.candidate_id AS candidate_id,
       collect(DISTINCT chg) AS changes,
       collect(DISTINCT a) AS approvals
"""


LIST_APPROVED_CANDIDATES = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
RETURN c
ORDER BY c.patient_id, c.encounter_id
"""


# ── Patient graph queries ──────────────────────────────────

LIST_PATIENTS = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id, count(e) AS encounter_count
ORDER BY patient_id
"""

GET_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id, count(e) AS encounter_count
"""

LIST_PATIENT_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, coded_count
ORDER BY e.date
LIMIT $limit
"""

GET_ENCOUNTER = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, coded_count
"""


# ── V3 Patient graph DOCUMENTS (semantic links) ─────────────

LIST_ENCOUNTER_CODED_LINKS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN toString(e.id) AS encounter_id,
       labels(s) AS node_labels,
       s.conceptId AS concept_id,
       s.name AS term,
       s.readCode AS read_code,
       s.semanticTag AS semantic_tag,
       r.evidence AS evidence,
       r.confidence AS confidence,
       r.domain AS domain,
       r.context AS context,
       r.modifiers AS modifiers,
       r.coded_at AS coded_at
ORDER BY r.coded_at DESC
"""

LIST_PATIENT_CODING_STATUS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id, coded_count
"""

DELETE_CODED_LINK = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE s.conceptId = $concept_id
DELETE r
"""


# ── Terminology search query ───────────────────────────────

TERMINOLOGY_SEARCH = """
CALL db.index.fulltext.queryNodes("term_fulltext", $q) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
WITH c, max(score) AS best_score,
     collect(DISTINCT rd.code)[0] AS read_code,
     collect(DISTINCT icd.code)[0] AS icd10
RETURN c.id AS snomed_concept_id,
       c.fsn AS term,
       c.semantic_tag AS semantic_tag,
       icd10,
       read_code,
       best_score AS score
ORDER BY best_score DESC
LIMIT $limit
"""
