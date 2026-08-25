"""Cypher for per-form schema nodes (:FormSchema).

A :FormSchema stores section-level annotation rules for a known referral
form. Once saved, the pipeline normaliser rewrites form text deterministically
and the quality gate is bypassed (score = 1.0).

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)

Node: :FormSchema
  schema_id     -- UUID (MERGE key)
  fingerprint   -- matches :FormFingerprint.fingerprint
  form_name     -- human-readable form name
  version       -- monotonically increasing integer
  status        -- "active" | "draft"
  sections_json -- JSON array of FormSection objects
  created_at    -- datetime
  updated_at    -- datetime
  created_by    -- user / service identity

Relationship: (:FormSchema)-[:SCHEMA_FOR]->(:FormFingerprint)
"""

FORM_SCHEMA_CONSTRAINTS = [
    (
        "CREATE CONSTRAINT form_schema_id IF NOT EXISTS "
        "FOR (s:FormSchema) REQUIRE s.schema_id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT form_schema_fingerprint IF NOT EXISTS "
        "FOR (s:FormSchema) REQUIRE s.fingerprint IS UNIQUE"
    ),
]

UPSERT_FORM_SCHEMA = """
MERGE (s:FormSchema {fingerprint: $fingerprint})
ON CREATE SET
    s.schema_id   = $schema_id,
    s.created_at  = datetime(),
    s.version     = 1
SET
    s.form_name     = $form_name,
    s.status        = $status,
    s.sections_json = $sections_json,
    s.updated_at    = datetime(),
    s.created_by    = $created_by
WITH s
MERGE (f:FormFingerprint {fingerprint: $fingerprint})
MERGE (s)-[:SCHEMA_FOR]->(f)
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.sections_json AS sections_json,
       s.created_at AS created_at,
       s.created_by AS created_by
"""

GET_FORM_SCHEMA_BY_FINGERPRINT = """
MATCH (s:FormSchema {fingerprint: $fingerprint})
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.sections_json AS sections_json,
       s.created_at AS created_at,
       s.created_by AS created_by
"""

LIST_FORM_SCHEMAS = """
MATCH (s:FormSchema)
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.created_at AS created_at
ORDER BY s.updated_at DESC
"""
