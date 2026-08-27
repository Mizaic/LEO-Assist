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
  organization_id -- existing :Organization.id
  service_id    -- existing :Service.id

Relationship: (:FormSchema)-[:SCHEMA_FOR]->(:FormFingerprint)
Relationship: (:FormSchema)-[:USED_BY_ORG]->(:Organization)
  Match Organization by id or ods_code. Do not create Organization.
Relationship: (:FormSchema)-[:USED_BY_SERVICE]->(:Service)
  Match Service by id or ers_service_id. Do not create Service.
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

SAVE_NORMALISED_TEMPLATE = """
MATCH (s:FormSchema {fingerprint: $fingerprint})
SET s.normalised_template = $normalised_template,
    s.chunk_section_map   = $chunk_section_map,
    s.updated_at          = datetime()
RETURN s.schema_id AS schema_id
"""

UPSERT_FORM_SCHEMA = """
MERGE (s:FormSchema {fingerprint: $fingerprint})
ON CREATE SET
    s.schema_id   = $schema_id,
    s.created_at  = datetime(),
    s.version     = 1
SET
    s.form_name        = $form_name,
    s.status           = $status,
    s.sections_json    = $sections_json,
    s.organization_id  = $organization_id,
    s.service_id       = $service_id,
    s.organization_name = $organization_name,
    s.service_name     = $service_name,
    s.organization_ods_code = $organization_ods_code,
    s.updated_at       = datetime(),
    s.created_by       = $created_by
WITH s
MERGE (f:FormFingerprint {fingerprint: $fingerprint})
MERGE (s)-[:SCHEMA_FOR]->(f)
WITH s
OPTIONAL MATCH (org:Organization)
WHERE $organization_id <> ''
  AND (org.id = $organization_id OR org.ods_code = $organization_id)
FOREACH (_ IN CASE WHEN org IS NOT NULL THEN [1] ELSE [] END |
    MERGE (s)-[:USED_BY_ORG]->(org)
)
WITH s
OPTIONAL MATCH (svc:Service)
WHERE $service_id <> ''
  AND (svc.id = $service_id OR svc.ers_service_id = $service_id)
FOREACH (_ IN CASE WHEN svc IS NOT NULL THEN [1] ELSE [] END |
    MERGE (s)-[:USED_BY_SERVICE]->(svc)
)
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.sections_json AS sections_json,
       s.created_at AS created_at,
       s.created_by AS created_by,
       s.organization_id AS organization_id,
       s.service_id AS service_id,
       s.organization_name AS organization_name,
       s.service_name AS service_name,
       s.organization_ods_code AS organization_ods_code
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
       s.created_by AS created_by,
       s.organization_id AS organization_id,
       s.service_id AS service_id,
       s.organization_name AS organization_name,
       s.service_name AS service_name,
       s.organization_ods_code AS organization_ods_code,
       s.chunk_section_map AS chunk_section_map
"""

GET_ACTIVE_FORM_SCHEMA_BY_ORG_SERVICE = """
MATCH (s:FormSchema)
WHERE s.status = 'active'
  AND s.organization_id = $organization_id
  AND s.service_id = $service_id
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.sections_json AS sections_json,
       s.created_at AS created_at,
       s.created_by AS created_by,
       s.organization_id AS organization_id,
       s.service_id AS service_id,
       s.organization_name AS organization_name,
       s.service_name AS service_name,
       s.organization_ods_code AS organization_ods_code,
       s.chunk_section_map AS chunk_section_map
ORDER BY s.updated_at DESC
LIMIT 1
"""

LIST_FORM_SCHEMAS = """
MATCH (s:FormSchema)
RETURN s.schema_id AS schema_id,
       s.fingerprint AS fingerprint,
       s.form_name AS form_name,
       s.version AS version,
       s.status AS status,
       s.created_at AS created_at,
       s.updated_at AS updated_at,
       s.organization_id AS organization_id,
       s.service_id AS service_id
ORDER BY s.updated_at DESC
"""

LIST_FORM_SCHEMA_SECTIONS = """
MATCH (s:FormSchema)
WHERE s.status = 'active'
RETURN s.fingerprint      AS fingerprint,
       s.form_name        AS form_name,
       s.organization_id  AS organization_id,
       s.service_id       AS service_id,
       s.sections_json    AS sections_json
"""

DELETE_FORM_SCHEMA = """
MATCH (s:FormSchema {fingerprint: $fingerprint})
WITH s, s.schema_id AS schema_id
DETACH DELETE s
RETURN schema_id
"""
