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
    c.source = $source,
    c.status = $status,
    c.schema_version = $schema_version,
    c.created_at = datetime(),
    c.updated_at = datetime()
ON MATCH SET
    c.text = $text,
    c.source = $source,
    c.status = $status,
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
    c.source AS source,
    c.status AS status,
    c.schema_version AS schema_version,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
"""

GET_TRAINING_CANDIDATES_PAGE = """
MATCH (c:TrainingCandidate)
WHERE ($status IS NULL OR c.status = $status)
  AND ($source IS NULL OR c.source = $source)
  AND ($search IS NULL OR toLower(c.text) CONTAINS toLower($search))
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
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
