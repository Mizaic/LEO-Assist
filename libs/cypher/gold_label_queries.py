"""Cypher queries for GDPR-isolated GoldLabel nodes."""

CREATE_GOLD_LABEL_INDEXES = [
    "CREATE CONSTRAINT gold_label_id IF NOT EXISTS FOR (g:GoldLabel) REQUIRE g.label_id IS UNIQUE",
    "CREATE INDEX gold_label_source IF NOT EXISTS FOR (g:GoldLabel) ON (g.source)",
    "CREATE INDEX gold_label_candidate IF NOT EXISTS FOR (g:GoldLabel) ON (g.candidate_id)",
]

UPSERT_GOLD_LABEL = """
MERGE (g:GoldLabel {label_id: $label_id})
ON CREATE SET
    g.text = $text,
    g.entities_json = $entities_json,
    g.quality_score = $quality_score,
    g.source = $source,
    g.verified_by = $verified_by,
    g.verified_at = datetime(),
    g.candidate_id = $candidate_id,
    g.schema_version = $schema_version,
    g.created_at = datetime(),
    g.updated_at = datetime()
ON MATCH SET
    g.text = $text,
    g.entities_json = $entities_json,
    g.quality_score = $quality_score,
    g.source = $source,
    g.verified_by = $verified_by,
    g.verified_at = datetime(),
    g.candidate_id = $candidate_id,
    g.schema_version = $schema_version,
    g.updated_at = datetime()
WITH g
OPTIONAL MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
    MERGE (c)-[:PRODUCED]->(g)
)
RETURN g.label_id AS label_id
"""

GET_GOLD_LABEL_BY_ID = """
MATCH (g:GoldLabel {label_id: $label_id})
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json,
    g.quality_score AS quality_score,
    g.source AS source,
    g.verified_by AS verified_by,
    toString(g.verified_at) AS verified_at,
    g.candidate_id AS candidate_id,
    g.schema_version AS schema_version,
    toString(g.created_at) AS created_at,
    toString(g.updated_at) AS updated_at
"""

GET_GOLD_LABEL_BY_CANDIDATE_ID = """
MATCH (g:GoldLabel {candidate_id: $candidate_id})
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json,
    g.quality_score AS quality_score,
    g.source AS source,
    g.verified_by AS verified_by,
    toString(g.verified_at) AS verified_at,
    g.candidate_id AS candidate_id,
    g.schema_version AS schema_version,
    toString(g.created_at) AS created_at,
    toString(g.updated_at) AS updated_at
ORDER BY g.updated_at DESC
LIMIT 1
"""

GET_GOLD_LABELS_PAGE = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
  AND ($source IS NULL OR g.source = $source)
  AND ($search IS NULL OR toLower(g.text) CONTAINS toLower($search))
  AND (
    $entity_label IS NULL
    OR toLower(g.entities_json) CONTAINS ('"label": "' + toLower($entity_label) + '"')
    OR toLower(g.entities_json) CONTAINS ('"semantic_tag": "' + toLower($entity_label) + '"')
  )
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json,
    g.quality_score AS quality_score,
    g.source AS source,
    g.verified_by AS verified_by,
    toString(g.verified_at) AS verified_at,
    g.candidate_id AS candidate_id,
    g.schema_version AS schema_version,
    toString(g.created_at) AS created_at,
    toString(g.updated_at) AS updated_at
ORDER BY g.updated_at DESC
SKIP $skip
LIMIT $limit
"""

COUNT_GOLD_LABELS_PAGE = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
  AND ($source IS NULL OR g.source = $source)
  AND ($search IS NULL OR toLower(g.text) CONTAINS toLower($search))
  AND (
    $entity_label IS NULL
    OR toLower(g.entities_json) CONTAINS ('"label": "' + toLower($entity_label) + '"')
    OR toLower(g.entities_json) CONTAINS ('"semantic_tag": "' + toLower($entity_label) + '"')
  )
RETURN count(g) AS total
"""

GET_GOLD_LABEL_STATS = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
RETURN
    count(g) AS total,
    avg(g.quality_score) AS avg_quality_score,
    sum(CASE WHEN g.quality_score >= 0.8 THEN 1 ELSE 0 END) AS high_quality
"""

GET_ALL_GOLD_LABELS_FOR_EXPORT = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE c.status = 'completed'
  AND g.entities_json IS NOT NULL
RETURN
    g.label_id AS label_id,
    g.text AS text,
    g.entities_json AS entities_json,
    g.source AS source,
    g.quality_score AS quality_score,
    toString(g.verified_at) AS verified_at
ORDER BY g.created_at ASC
"""

UPDATE_GOLD_LABEL_ENTITIES = """
MATCH (g:GoldLabel {label_id: $label_id})
SET g.entities_json = $entities_json,
    g.updated_at    = datetime()
WITH g
OPTIONAL MATCH (c:TrainingCandidate {candidate_id: g.candidate_id})
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
    SET c.entities_json = $entities_json,
        c.updated_at    = datetime()
)
RETURN g.label_id AS label_id, g.entities_json AS entities_json
"""

DELETE_GOLD_LABEL_AND_RESET_CANDIDATE = """
MATCH (g:GoldLabel {label_id: $label_id})
OPTIONAL MATCH (c:TrainingCandidate {candidate_id: g.candidate_id})
OPTIONAL MATCH (:TrainingCandidate)-[rel:PRODUCED]->(g)
WITH g, c, collect(rel) AS rels, g.label_id AS deleted_label_id
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
    SET c.status = 'pending',
        c.updated_at = datetime()
)
FOREACH (r IN rels | DELETE r)
WITH g, c, deleted_label_id
DELETE g
RETURN
    deleted_label_id AS label_id,
    c.candidate_id AS candidate_id,
    CASE WHEN c IS NULL THEN false ELSE true END AS candidate_reset,
    CASE WHEN c IS NULL THEN null ELSE c.status END AS candidate_status
"""
