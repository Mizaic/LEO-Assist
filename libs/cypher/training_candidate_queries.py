"""Cypher queries for GDPR-isolated TrainingCandidate nodes.

TrainingCandidate is the anonymized learning-loop input. It MUST NOT contain
patient, encounter, tenant, or organization identifiers.
"""

CREATE_TRAINING_CANDIDATE_INDEXES = [
    "CREATE CONSTRAINT training_candidate_id IF NOT EXISTS FOR (c:TrainingCandidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE INDEX training_candidate_status IF NOT EXISTS FOR (c:TrainingCandidate) ON (c.status)",
    "CREATE INDEX training_candidate_source IF NOT EXISTS FOR (c:TrainingCandidate) ON (c.source)",
]

UPSERT_TRAINING_CANDIDATE = """
MERGE (c:TrainingCandidate {candidate_id: $candidate_id})
ON CREATE SET
    c.text = $text,
    c.entities_json = $entities_json,
    c.source = $source,
    c.status = $status,
    c.schema_version = $schema_version,
    c.created_at = datetime(),
    c.updated_at = datetime()
ON MATCH SET
    c.text = $text,
    c.entities_json = $entities_json,
    c.source = $source,
    c.status = CASE
        WHEN c.status = 'completed' AND $status = 'pending' THEN c.status
        ELSE $status
    END,
    c.schema_version = $schema_version,
    c.updated_at = datetime()
RETURN c.candidate_id AS candidate_id, c.status AS status
"""

UPDATE_TRAINING_CANDIDATE_STATUS = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
SET c.status = $status,
    c.updated_at = datetime()
RETURN c.candidate_id AS candidate_id, c.status AS status
"""

GET_TRAINING_CANDIDATE_BY_ID = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.source AS source,
    c.status AS status,
    c.schema_version AS schema_version,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
"""

GET_TRAINING_CANDIDATES_PAGE = """
MATCH (c:TrainingCandidate)
WHERE ($status IS NULL OR c.status = $status)
  AND ($exclude_completed = false OR c.status <> 'completed')
  AND ($source IS NULL OR c.source = $source)
  AND ($search IS NULL OR toLower(c.text) CONTAINS toLower($search))
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.source AS source,
    c.status AS status,
    c.schema_version AS schema_version,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
ORDER BY c.updated_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_TRAINING_CANDIDATES_PAGE = """
MATCH (c:TrainingCandidate)
WHERE ($status IS NULL OR c.status = $status)
  AND ($exclude_completed = false OR c.status <> 'completed')
  AND ($source IS NULL OR c.source = $source)
  AND ($search IS NULL OR toLower(c.text) CONTAINS toLower($search))
RETURN count(c) AS total
"""

GET_TRAINING_CANDIDATE_STATS = """
MATCH (c:TrainingCandidate)
WITH
    count(c) AS total,
    sum(CASE WHEN c.status = 'pending' THEN 1 ELSE 0 END) AS pending,
    sum(CASE WHEN c.status = 'processing' THEN 1 ELSE 0 END) AS processing,
    sum(CASE WHEN c.status = 'completed' THEN 1 ELSE 0 END) AS completed,
    sum(CASE WHEN c.status = 'failed' THEN 1 ELSE 0 END) AS failed
RETURN total, pending, processing, completed, failed
"""

DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
OPTIONAL MATCH (gl:GoldLabel {candidate_id: $candidate_id})
WITH c, collect(DISTINCT gl) AS gold_labels
OPTIONAL MATCH (sf:SurfaceFormTask {candidate_id: $candidate_id})
WITH c, gold_labels, collect(DISTINCT sf) AS surface_form_tasks
FOREACH (n IN gold_labels | DETACH DELETE n)
FOREACH (n IN surface_form_tasks | DETACH DELETE n)
WITH c, size(gold_labels) AS gold_labels_deleted, size(surface_form_tasks) AS surface_form_tasks_deleted
DETACH DELETE c
RETURN
    $candidate_id AS candidate_id,
    gold_labels_deleted AS gold_labels_deleted,
    surface_form_tasks_deleted AS surface_form_tasks_deleted
"""

MARK_TRAINING_CANDIDATE_DUPLICATES = """
UNWIND $updates AS u
MATCH (d:TrainingCandidate {candidate_id: u.duplicate_id})
MATCH (c:TrainingCandidate {candidate_id: u.canonical_id})
SET
    d.dedupe_status = 'duplicate',
    d.canonical_candidate_id = u.canonical_id,
    d.dedupe_score = toFloat(u.score),
    d.dedupe_method = u.method,
    d.dedupe_run_id = $run_id,
    d.dedupe_updated_at = datetime(),
    d.updated_at = datetime(),
    c.dedupe_status = coalesce(c.dedupe_status, 'canonical'),
    c.dedupe_run_id = $run_id,
    c.dedupe_updated_at = datetime(),
    c.updated_at = datetime()
RETURN count(d) AS duplicates_marked
"""
