"""Cypher queries for FHIR-aligned Device nodes.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

Each Device node represents a configurable AI model (LLM, NER, ML).
Sensitive credentials stay in env vars / Key Vault — Neo4j stores only
the catalog metadata, enabled/disabled status, and which device is active
for each role (small / big / max).

FHIR Device alignment:
  resourceType  : "Device"
  id            : device_id
  deviceName[0] : name
  type.code     : device_type  ("llm" | "ner" | "ml")
  status        : status       ("active" | "inactive")
  manufacturer  : provider     ("AWS Bedrock" | "Azure OpenAI" | "Custom")
  property[]    : role, env_var, default_model_id, endpoint_env_var
"""

CREATE_DEVICE_INDEXES = [
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE CONSTRAINT device_env_var_not_null IF NOT EXISTS FOR (d:Device) REQUIRE d.env_var IS NOT NULL",
    "CREATE INDEX device_type IF NOT EXISTS FOR (d:Device) ON (d.device_type)",
    "CREATE INDEX device_status IF NOT EXISTS FOR (d:Device) ON (d.status)",
]

# --------------------------------------------------------------------------
# Upsert a single Device record
# --------------------------------------------------------------------------
UPSERT_DEVICE = """
MERGE (d:Device {device_id: $device_id})
ON CREATE SET
    d.name              = $name,
    d.provider          = $provider,
    d.device_type       = $device_type,
    d.role              = $role,
    d.status            = $status,
    d.env_var           = coalesce($env_var, ''),
    d.default_model_id  = coalesce($default_model_id, ''),
    d.endpoint_env_var  = coalesce($endpoint_env_var, ''),
    d.notes             = coalesce($notes, ''),
    d.raw_json          = coalesce($raw_json, ''),
    d.schema_version    = '1.0',
    d.created_at        = datetime(),
    d.updated_at        = datetime()
ON MATCH SET
    d.name              = $name,
    d.provider          = $provider,
    d.device_type       = $device_type,
    d.role              = $role,
    d.env_var           = coalesce($env_var, ''),
    d.default_model_id  = coalesce($default_model_id, ''),
    d.endpoint_env_var  = coalesce($endpoint_env_var, ''),
    d.notes             = coalesce($notes, ''),
    d.raw_json          = coalesce($raw_json, ''),
    d.updated_at        = datetime()
RETURN d.device_id AS device_id
"""

# --------------------------------------------------------------------------
# List all Devices (ordered by type, then role)
# --------------------------------------------------------------------------
LIST_DEVICES = """
MATCH (d:Device)
RETURN
    d.device_id         AS device_id,
    d.name              AS name,
    d.provider          AS provider,
    d.device_type       AS device_type,
    d.role              AS role,
    d.status            AS status,
    d.env_var           AS env_var,
    d.default_model_id  AS default_model_id,
    d.endpoint_env_var  AS endpoint_env_var,
    d.notes             AS notes,
    toString(d.updated_at) AS updated_at
ORDER BY d.device_type ASC, d.role ASC, d.name ASC
"""

# --------------------------------------------------------------------------
# Get a single Device by id
# --------------------------------------------------------------------------
GET_DEVICE = """
MATCH (d:Device {device_id: $device_id})
RETURN
    d.device_id         AS device_id,
    d.name              AS name,
    d.provider          AS provider,
    d.device_type       AS device_type,
    d.role              AS role,
    d.status            AS status,
    d.env_var           AS env_var,
    d.default_model_id  AS default_model_id,
    d.endpoint_env_var  AS endpoint_env_var,
    d.notes             AS notes,
    d.raw_json          AS raw_json,
    toString(d.updated_at) AS updated_at
"""

# --------------------------------------------------------------------------
# Enable / disable a Device (status flip)
# --------------------------------------------------------------------------
SET_DEVICE_STATUS = """
MATCH (d:Device {device_id: $device_id})
SET d.status = $status, d.updated_at = datetime()
RETURN d.device_id AS device_id, d.status AS status
"""

# --------------------------------------------------------------------------
# Pipeline config node — stores which provider + tier the pipeline uses.
# There is exactly one PipelineConfig node (singleton, upserted by id).
# --------------------------------------------------------------------------
UPSERT_PIPELINE_CONFIG = """
MERGE (c:PipelineConfig {config_id: 'default'})
ON CREATE SET
    c.provider          = $provider,
    c.tier              = $tier,
    c.extractor_backend = $extractor_backend,
    c.strict            = $strict,
    c.consensus_mode    = $consensus_mode,
    c.created_at        = datetime(),
    c.updated_at        = datetime()
ON MATCH SET
    c.provider          = $provider,
    c.tier              = $tier,
    c.extractor_backend = $extractor_backend,
    c.strict            = $strict,
    c.consensus_mode    = $consensus_mode,
    c.updated_at        = datetime()
RETURN c.config_id AS config_id
"""

GET_PIPELINE_CONFIG = """
MATCH (c:PipelineConfig {config_id: 'default'})
RETURN
    c.provider          AS provider,
    c.tier              AS tier,
    c.extractor_backend AS extractor_backend,
    c.strict            AS strict,
    coalesce(c.consensus_mode, false) AS consensus_mode,
    toString(c.updated_at) AS updated_at
"""
