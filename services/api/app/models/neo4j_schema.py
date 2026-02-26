"""Neo4j schema and write/query templates for HITL MVP."""

from __future__ import annotations

PATIENT_SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT encounter_candidate_id IF NOT EXISTS FOR (c:EncounterCandidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE CONSTRAINT review_task_id IF NOT EXISTS FOR (t:ReviewTask) REQUIRE t.task_id IS UNIQUE",
    "CREATE CONSTRAINT approval_id IF NOT EXISTS FOR (a:Approval) REQUIRE a.approval_id IS UNIQUE",
    "CREATE CONSTRAINT change_id IF NOT EXISTS FOR (chg:Change) REQUIRE chg.change_id IS UNIQUE",
    "CREATE INDEX review_task_status IF NOT EXISTS FOR (t:ReviewTask) ON (t.status)",
    "CREATE INDEX review_task_priority IF NOT EXISTS FOR (t:ReviewTask) ON (t.priority)",
    "CREATE CONSTRAINT game_score_id IF NOT EXISTS FOR (gs:GameScore) REQUIRE gs.id IS UNIQUE",
    "CREATE INDEX game_score_game IF NOT EXISTS FOR (gs:GameScore) ON (gs.game)",
    # Multi-tenancy indexes
    "CREATE INDEX patient_tenant IF NOT EXISTS FOR (p:Patient) ON (p.tenantId)",
    "CREATE INDEX encounter_candidate_tenant IF NOT EXISTS FOR (c:EncounterCandidate) ON (c.tenantId)",
    "CREATE INDEX review_task_tenant IF NOT EXISTS FOR (t:ReviewTask) ON (t.tenantId)",
    "CREATE INDEX organization_id IF NOT EXISTS FOR (o:Organization) ON (o.id)",
]

CODING_SCHEMA_CONSTRAINTS: list[str] = [
    'CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS FOR (sf:SurfaceForm) ON EACH [sf.form]',
    "CREATE CONSTRAINT surface_form_normalized IF NOT EXISTS FOR (sf:SurfaceForm) REQUIRE sf.normalized IS UNIQUE",
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
    c.llm_usage_json = $llm_usage_json,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime())
"""


CREATE_REVIEW_TASK = """
MATCH (c:EncounterCandidate {candidate_id: $candidate_id})
MERGE (c)-[:HAS_TASK]->(t:ReviewTask {task_id: $task_id})
ON CREATE SET
    t.priority = $priority,
    t.status = $status,
    t.assigned_reviewer = $assigned_reviewer,
    t.warning_count = $warning_count,
    t.created_at = datetime(),
    t.updated_at = datetime()
ON MATCH SET
    t.priority = $priority,
    t.warning_count = $warning_count,
    t.updated_at = datetime(),
    t.status = CASE WHEN t.status IN ['approved', 'rejected', 'escalated'] THEN t.status ELSE $status END
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
ORDER BY t.priority DESC, c.date DESC
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

LIST_APPROVED_CANDIDATES_FOR_PATIENT = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved' AND c.patient_id = $patient_id
RETURN c
ORDER BY c.encounter_id
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


# ── Patient graph queries ──────────────────────────────────

LIST_PATIENTS = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id, count(e) AS encounter_count
ORDER BY patient_id
"""

# Patient graph: approved count per patient (EncounterCandidate lives here)
LIST_APPROVED_COUNT_BY_PATIENT = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
RETURN c.patient_id AS patient_id, count(*) AS reviewed_count
"""

GET_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
RETURN toString(p.id) AS patient_id,
       count(e) AS encounter_count,
       p.gender AS gender,
       toString(p.birthDate) AS birth_date
"""

LIST_PATIENT_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, coded_count, e.flags AS flags
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

UPDATE_CODED_LINK_MODIFIERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->(s)
WHERE s.conceptId = $concept_id
SET r.modifiers = $modifiers
RETURN s.conceptId AS concept_id, r.modifiers AS modifiers
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


# ── Terminology search query ───────────────────────────────

# ── Encounter search queries ──────────────────────────────

SEARCH_ENCOUNTERS_KEYWORD = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toLower(e.text) CONTAINS toLower($q)
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags
ORDER BY e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_BY_CONCEPT_DOCS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c:Concept)
WHERE toString(p.id) = $patient_id AND c.id IN $concept_ids
WITH e, collect(DISTINCT c.id) AS matched_concepts
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, matched_concepts, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags,
       matched_concepts
ORDER BY size(matched_concepts) DESC, e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_BY_CONCEPT_CANDIDATES = """
MATCH (ec:EncounterCandidate)
WHERE ec.patient_id = $patient_id
  AND any(cid IN $concept_ids WHERE ec.sentences_json CONTAINS cid)
WITH collect(DISTINCT ec.encounter_id) AS eids
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) IN eids
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags
ORDER BY e.date DESC
LIMIT $limit
"""

SEARCH_ENCOUNTERS_VECTOR = """
CALL db.index.vector.queryNodes('encounter_vector_index', $k, $query_vector)
YIELD node, score
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(node)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (node)-[r:DOCUMENTS]->()
WITH node AS e, score, count(r) AS coded_count
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       e.text AS text,
       coded_count,
       e.flags AS flags,
       score AS similarity
ORDER BY score DESC
LIMIT $limit
"""


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
