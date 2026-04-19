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
    c.relation_changes = $relation_changes,
    c.source = $source,
    c.status = $status,
    c.hitl_reason = $hitl_reason,
    c.hitl_guidance = $hitl_guidance,
    c.schema_version = $schema_version,
    c.created_at = datetime(),
    c.updated_at = datetime()
ON MATCH SET
    c.text = $text,
    c.entities_json = $entities_json,
    c.relation_changes = $relation_changes,
    c.source = $source,
    c.status = CASE
        WHEN c.status = 'completed' AND $status = 'pending' THEN c.status
        ELSE $status
    END,
    c.hitl_reason = $hitl_reason,
    c.hitl_guidance = $hitl_guidance,
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

# Atomic write of an AI first-pass result (DI-LEO-AI-208, R-LEO-AI-197).
# - entities_json is overwritten with the AI pass.
# - entities_json_original is set ONCE: the existing entities_json is moved
#   into entities_json_original ONLY IF entities_json_original is currently
#   null (write-once audit copy invariant).
# - Refuses to write when c.status = 'completed' (TOCTOU defence; gold
#   records are never modified by the AI first-pass).
UPSERT_AI_FIRST_PASS_ENTITIES = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
WHERE c.status <> 'completed'
SET c.entities_json_original = CASE
        WHEN c.entities_json_original IS NULL THEN c.entities_json
        ELSE c.entities_json_original
    END,
    c.entities_json = $entities_json,
    c.ai_first_pass_run_id = $run_id,
    c.ai_first_pass_at = datetime(),
    c.updated_at = datetime()
RETURN
    c.candidate_id AS candidate_id,
    c.status AS status,
    c.ai_first_pass_run_id AS ai_first_pass_run_id,
    toString(c.ai_first_pass_at) AS ai_first_pass_at,
    (c.entities_json_original IS NOT NULL) AS audit_copy_present
"""

# Read the gold-completed candidate pool for FewShotSelector.
# Returns text + entities_json so the selector can rank by cosine and the
# extractor can pass exemplars to Haiku verbatim. Capped to keep the
# in-memory embedding pool bounded.
READ_GOLD_POOL_FOR_FEW_SHOT = """
MATCH (c:TrainingCandidate {status: 'completed'})
WHERE c.text IS NOT NULL AND c.entities_json IS NOT NULL
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.source AS source
ORDER BY c.updated_at DESC
LIMIT $limit
"""

GET_TRAINING_CANDIDATE_BY_ID = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.entities_json_original AS entities_json_original,
    c.ai_first_pass_run_id AS ai_first_pass_run_id,
    toString(c.ai_first_pass_at) AS ai_first_pass_at,
    c.relation_changes AS relation_changes,
    c.source AS source,
    c.status AS status,
    c.hitl_reason AS hitl_reason,
    c.hitl_guidance AS hitl_guidance,
    c.schema_version AS schema_version,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
"""

# DI-LEO-AI-526 -- the dry-run review queue accepts an optional `$terms`
# array of pre-expanded lower-case search terms (typo-corrected and
# synonym-expanded by the API router via libs.search.term_expansion).
# When `$terms` is non-empty we OR-match across the list so a search for
# "lump" also surfaces rows that wrote "mass", "swelling", or "nodule",
# matching the host-search vocabulary on /care/encounters. When `$terms`
# is empty we fall back to the legacy `$search` substring filter so
# callers that have not opted in to expansion continue to work.
GET_TRAINING_CANDIDATES_PAGE = """
MATCH (c:TrainingCandidate)
WHERE ($status IS NULL OR c.status = $status)
  AND ($exclude_completed = false OR c.status <> 'completed')
  AND ($source IS NULL OR c.source = $source)
  AND (
    CASE
      WHEN $terms IS NOT NULL AND size($terms) > 0
        THEN ANY(t IN $terms WHERE toLower(c.text) CONTAINS t)
      WHEN $search IS NOT NULL
        THEN toLower(c.text) CONTAINS toLower($search)
      ELSE true
    END
  )
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.entities_json_original AS entities_json_original,
    c.ai_first_pass_run_id AS ai_first_pass_run_id,
    toString(c.ai_first_pass_at) AS ai_first_pass_at,
    c.relation_changes AS relation_changes,
    c.source AS source,
    c.status AS status,
    c.hitl_reason AS hitl_reason,
    c.hitl_guidance AS hitl_guidance,
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
  AND (
    CASE
      WHEN $terms IS NOT NULL AND size($terms) > 0
        THEN ANY(t IN $terms WHERE toLower(c.text) CONTAINS t)
      WHEN $search IS NOT NULL
        THEN toLower(c.text) CONTAINS toLower($search)
      ELSE true
    END
  )
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

GET_ACTIVE_LEARNING_QUEUE = """
MATCH (c:TrainingCandidate)
WHERE c.status = 'pending'
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.relation_changes AS relation_changes,
    c.source AS source,
    c.uncertainty_score AS uncertainty_score,
    c.hitl_reason AS hitl_reason,
    c.hitl_guidance AS hitl_guidance,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
ORDER BY
    CASE WHEN c.uncertainty_score IS NULL THEN 0 ELSE c.uncertainty_score END DESC,
    c.created_at ASC
SKIP $skip
LIMIT $limit
"""

# Fetches all pending candidates for Python-side rarity re-ranking.
# Capped at 2000 to keep response time acceptable; new arrivals rotate in
# as earlier items are reviewed and move out of the pending pool.
GET_ALL_PENDING_FOR_RANKING = """
MATCH (c:TrainingCandidate)
WHERE c.status = 'pending'
RETURN
    c.candidate_id AS candidate_id,
    c.text AS text,
    c.entities_json AS entities_json,
    c.relation_changes AS relation_changes,
    c.source AS source,
    c.uncertainty_score AS uncertainty_score,
    c.hitl_reason AS hitl_reason,
    c.hitl_guidance AS hitl_guidance,
    toString(c.created_at) AS created_at,
    toString(c.updated_at) AS updated_at
ORDER BY c.created_at ASC
LIMIT 2000
"""

COUNT_ACTIVE_LEARNING_QUEUE = """
MATCH (c:TrainingCandidate)
WHERE c.status = 'pending'
RETURN count(c) AS total
"""

GET_PENDING_CANDIDATES_FOR_SCORING = """
MATCH (c:TrainingCandidate)
WHERE c.status = 'pending'
  AND c.text IS NOT NULL
RETURN c.candidate_id AS candidate_id, c.text AS text
ORDER BY c.created_at ASC
LIMIT 5000
"""

SET_UNCERTAINTY_SCORE = """
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
SET c.uncertainty_score = $score, c.uncertainty_scored_at = datetime()
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
