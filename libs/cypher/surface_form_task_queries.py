"""Cypher queries for SurfaceFormTask review workflow."""

import uuid

CREATE_SURFACE_FORM_TASK_INDEXES = [
    "CREATE CONSTRAINT surface_form_task_id IF NOT EXISTS FOR (t:SurfaceFormTask) REQUIRE t.task_id IS UNIQUE",
    "CREATE INDEX surface_form_task_status IF NOT EXISTS FOR (t:SurfaceFormTask) ON (t.status)",
    "CREATE INDEX surface_form_task_candidate IF NOT EXISTS FOR (t:SurfaceFormTask) ON (t.candidate_id)",
]

UPSERT_SURFACE_FORM_TASK = """
MERGE (t:SurfaceFormTask {task_id: $task_id})
ON CREATE SET
    t.entity_text = $entity_text,
    t.current_concept = $current_concept,
    t.current_term = $current_term,
    t.suggested_concept = $suggested_concept,
    t.suggested_term = $suggested_term,
    t.candidates_json = $candidates_json,
    t.context_text = $context_text,
    t.candidate_id = $candidate_id,
    t.confidence = $confidence,
    t.status = 'pending',
    t.created_at = datetime()
ON MATCH SET
    t.suggested_concept = $suggested_concept,
    t.suggested_term = $suggested_term,
    t.candidates_json = $candidates_json,
    t.context_text = $context_text,
    t.confidence = $confidence
WITH t
OPTIONAL MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
    MERGE (c)-[:HAS_SURFACE_FORM_TASK]->(t)
)
RETURN t.task_id AS task_id, t.status AS status
"""

LIST_PENDING_SURFACE_FORM_TASKS = """
MATCH (t:SurfaceFormTask)
WHERE ($status IS NULL OR t.status = $status)
RETURN
    t.task_id AS task_id,
    t.entity_text AS entity_text,
    t.current_concept AS current_concept,
    t.current_term AS current_term,
    t.suggested_concept AS suggested_concept,
    t.suggested_term AS suggested_term,
    t.candidate_id AS candidate_id,
    t.confidence AS confidence,
    t.status AS status,
    toString(t.created_at) AS created_at
ORDER BY t.created_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_SURFACE_FORM_TASKS = """
MATCH (t:SurfaceFormTask)
WHERE ($status IS NULL OR t.status = $status)
RETURN count(t) AS total
"""

GET_SURFACE_FORM_TASK_BY_ID = """
MATCH (t:SurfaceFormTask {task_id: $task_id})
RETURN
    t.task_id AS task_id,
    t.entity_text AS entity_text,
    t.current_concept AS current_concept,
    t.current_term AS current_term,
    t.suggested_concept AS suggested_concept,
    t.suggested_term AS suggested_term,
    t.candidates_json AS candidates_json,
    t.context_text AS context_text,
    t.candidate_id AS candidate_id,
    t.confidence AS confidence,
    t.status AS status,
    t.resolved_concept AS resolved_concept,
    t.resolved_by AS resolved_by,
    toString(t.resolved_at) AS resolved_at,
    toString(t.created_at) AS created_at
"""

RESOLVE_SURFACE_FORM_TASK = """
MATCH (t:SurfaceFormTask {task_id: $task_id})
SET
    t.status = $status,
    t.resolved_concept = $resolved_concept,
    t.resolved_by = $resolved_by,
    t.resolved_at = datetime()
RETURN t.task_id AS task_id, t.status AS status
"""

DELETE_ALL_SURFACE_FORM_TASKS = """
MATCH (t:SurfaceFormTask)
DETACH DELETE t
"""


def make_surface_form_task_id(candidate_id: str, entity_text: str, current_concept: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{candidate_id}|{entity_text}|{current_concept}"))
