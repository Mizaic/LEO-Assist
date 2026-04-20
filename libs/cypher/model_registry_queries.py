"""Cypher queries for ModelVersion nodes in the Patient Graph.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

Model manifests are stored as (:ModelVersion) nodes. One (:ModelRegistryConfig)
singleton holds the active_version pointer.
"""

CREATE_MODEL_VERSION = """
MERGE (m:ModelVersion {version: $version})
SET m.model_name = $model_name,
    m.model_path = $model_path,
    m.training_dataset_version = $training_dataset_version,
    m.schema_version = $schema_version,
    m.deid_version = $deid_version,
    m.artifact_uri = $artifact_uri,
    m.status = $status,
    m.offline_precision = $offline_precision,
    m.offline_recall = $offline_recall,
    m.canary_precision = $canary_precision,
    m.canary_recall = $canary_recall,
    m.canary_cohort = $canary_cohort,
    m.rollback_target_version = $rollback_target_version,
    m.registered_at = $registered_at,
    m.promoted_at = $promoted_at,
    m.notes = $notes
RETURN m.version AS version
"""

GET_MODEL_VERSION = """
MATCH (m:ModelVersion {version: $version})
RETURN m.model_name AS model_name,
       m.version AS model_version,
       m.model_path AS model_path,
       m.training_dataset_version AS training_dataset_version,
       m.schema_version AS schema_version,
       m.deid_version AS deid_version,
       m.artifact_uri AS artifact_uri,
       m.status AS status,
       m.offline_precision AS offline_precision,
       m.offline_recall AS offline_recall,
       m.canary_precision AS canary_precision,
       m.canary_recall AS canary_recall,
       m.canary_cohort AS canary_cohort,
       m.rollback_target_version AS rollback_target_version,
       m.registered_at AS registered_at,
       m.promoted_at AS promoted_at,
       m.notes AS notes
"""

LIST_MODEL_VERSIONS = """
MATCH (m:ModelVersion)
RETURN m.model_name AS model_name,
       m.version AS model_version,
       m.model_path AS model_path,
       m.training_dataset_version AS training_dataset_version,
       m.schema_version AS schema_version,
       m.deid_version AS deid_version,
       m.artifact_uri AS artifact_uri,
       m.status AS status,
       m.offline_precision AS offline_precision,
       m.offline_recall AS offline_recall,
       m.canary_precision AS canary_precision,
       m.canary_recall AS canary_recall,
       m.canary_cohort AS canary_cohort,
       m.rollback_target_version AS rollback_target_version,
       m.registered_at AS registered_at,
       m.promoted_at AS promoted_at,
       m.notes AS notes
ORDER BY m.registered_at DESC
"""

GET_ACTIVE_VERSION = """
MATCH (c:ModelRegistryConfig)
WHERE c.id = 'default'
RETURN c.active_version AS active_version
"""

SET_ACTIVE_VERSION = """
MERGE (c:ModelRegistryConfig {id: 'default'})
SET c.active_version = $active_version
RETURN c.active_version AS active_version
"""

UPDATE_MODEL_VERSION = """
MATCH (m:ModelVersion {version: $version})
SET m += $updates
RETURN m.version AS version
"""
