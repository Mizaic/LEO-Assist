"""Cypher queries for ModelConfig nodes in the Knowledge Graph.

ModelConfig is the single source of truth for cost estimation and spend
reporting. Env vars are only used as a bootstrap when no nodes exist yet
(fresh instance or DR restore).
"""

COUNT_MODEL_CONFIGS = """
MATCH (m:ModelConfig) RETURN count(m) AS total
"""

CREATE_MODEL_CONFIG = """
CREATE (m:ModelConfig {
  key:                $key,
  provider:           $provider,
  tier:               $tier,
  display_name:       $display_name,
  model_id:           $model_id,
  cost_per_1m_input:  $cost_per_1m_input,
  cost_per_1m_cached: $cost_per_1m_cached,
  cost_per_1m_output: $cost_per_1m_output,
  is_active:          $is_active,
  source:             'user',
  created_at:         datetime(),
  updated_at:         datetime()
})
RETURN m.key AS key
"""

DELETE_MODEL_CONFIG = """
MATCH (m:ModelConfig {key: $key})
DELETE m
RETURN count(*) AS deleted
"""

CREATE_CONSTRAINT_MODEL_CONFIG = """
CREATE CONSTRAINT model_config_key IF NOT EXISTS
FOR (m:ModelConfig) REQUIRE m.key IS UNIQUE
"""

UPSERT_MODEL_CONFIG = """
MERGE (m:ModelConfig {key: $key})
ON CREATE SET
  m.provider              = $provider,
  m.tier                  = $tier,
  m.display_name          = $display_name,
  m.model_id              = $model_id,
  m.cost_per_1m_input     = $cost_per_1m_input,
  m.cost_per_1m_cached    = $cost_per_1m_cached,
  m.cost_per_1m_output    = $cost_per_1m_output,
  m.is_active             = $is_active,
  m.source                = 'seed',
  m.created_at            = datetime(),
  m.updated_at            = datetime()
ON MATCH SET
  m.display_name          = CASE WHEN m.source = 'seed' THEN $display_name ELSE m.display_name END,
  m.model_id              = CASE WHEN m.source = 'seed' THEN $model_id ELSE m.model_id END,
  m.cost_per_1m_input     = CASE WHEN m.source = 'seed' THEN $cost_per_1m_input ELSE m.cost_per_1m_input END,
  m.cost_per_1m_cached    = CASE WHEN m.source = 'seed' THEN $cost_per_1m_cached ELSE m.cost_per_1m_cached END,
  m.cost_per_1m_output    = CASE WHEN m.source = 'seed' THEN $cost_per_1m_output ELSE m.cost_per_1m_output END,
  m.updated_at            = datetime()
RETURN m.key AS key, m.source AS source
"""

LIST_MODEL_CONFIGS = """
MATCH (m:ModelConfig)
RETURN m.key                AS key,
       m.provider           AS provider,
       m.tier               AS tier,
       m.display_name       AS displayName,
       m.model_id           AS modelId,
       m.cost_per_1m_input  AS costPer1mInput,
       m.cost_per_1m_cached AS costPer1mCachedInput,
       m.cost_per_1m_output AS costPer1mOutput,
       m.is_active          AS isActive,
       m.source             AS source,
       m.updated_at         AS updatedAt
ORDER BY m.provider, m.tier
"""

GET_MODEL_CONFIG = """
MATCH (m:ModelConfig {key: $key})
RETURN m.key                AS key,
       m.provider           AS provider,
       m.tier               AS tier,
       m.display_name       AS displayName,
       m.model_id           AS modelId,
       m.cost_per_1m_input  AS costPer1mInput,
       m.cost_per_1m_cached AS costPer1mCachedInput,
       m.cost_per_1m_output AS costPer1mOutput,
       m.is_active          AS isActive,
       m.source             AS source,
       m.updated_at         AS updatedAt
"""

UPDATE_MODEL_CONFIG = """
MATCH (m:ModelConfig {key: $key})
SET m.display_name      = $display_name,
    m.model_id          = $model_id,
    m.cost_per_1m_input = $cost_per_1m_input,
    m.cost_per_1m_cached= $cost_per_1m_cached,
    m.cost_per_1m_output= $cost_per_1m_output,
    m.is_active         = $is_active,
    m.source            = 'user',
    m.updated_at        = datetime()
RETURN m.key AS key
"""

# ── Spend aggregation ────────────────────────────────────────────────────────

GET_PATIENT_LLM_SPEND = """
MATCH (c:EncounterCandidate {patient_id: $patient_id})
WHERE c.llm_usage_json IS NOT NULL
  AND ($from_date IS NULL OR c.updated_at >= datetime($from_date))
  AND ($to_date   IS NULL OR c.updated_at <= datetime($to_date))
RETURN c.candidate_id          AS candidateId,
       c.encounter_id          AS encounterId,
       c.updated_at            AS updatedAt,
       c.extraction_model_name AS modelName,
       c.llm_usage_json        AS llmUsageJson
ORDER BY c.updated_at DESC
"""

GET_ORG_LLM_SPEND = """
MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
WHERE gp.id = $org_id OR ($org_id IS NULL)
MATCH (c:EncounterCandidate {patient_id: p.id})
WHERE c.llm_usage_json IS NOT NULL
  AND ($from_date IS NULL OR c.updated_at >= datetime($from_date))
  AND ($to_date   IS NULL OR c.updated_at <= datetime($to_date))
RETURN c.extraction_model_name AS modelName,
       count(c)                AS candidateCount,
       sum(toInteger(apoc.convert.fromJsonMap(c.llm_usage_json).input_tokens))         AS totalInputTokens,
       sum(toInteger(apoc.convert.fromJsonMap(c.llm_usage_json).output_tokens))        AS totalOutputTokens,
       sum(toInteger(apoc.convert.fromJsonMap(c.llm_usage_json).cached_input_tokens))  AS totalCachedTokens,
       sum(toFloat(apoc.convert.fromJsonMap(c.llm_usage_json).cost_usd))               AS totalCostUsd
"""

_AUDIT_EVENT_WHERE = """
WHERE ae.type = 'PipelineRun'
  AND ae.llm_input_tokens IS NOT NULL
  AND ($patient_id IS NULL OR ae.patient_id = $patient_id)
  AND ($from_date  IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date    IS NULL OR ae.created_at <= datetime($to_date))
  AND ($is_admin = true OR EXISTS {
    MATCH (ae_p:Patient {id: ae.patient_id})-[:HAS_GENERAL_PRACTITIONER]->(ae_gp)
    WHERE ae_gp.id IN $org_ids
  })
"""

GET_AUDIT_EVENT_SPEND = (
    "MATCH (ae:AuditEvent) "
    + _AUDIT_EVENT_WHERE
    + """RETURN ae.run_id             AS runId,
       ae.patient_id         AS patientId,
       ae.encounter_id       AS encounterId,
       ae.status             AS status,
       ae.total_duration_ms  AS durationMs,
       ae.llm_input_tokens   AS inputTokens,
       ae.llm_output_tokens  AS outputTokens,
       ae.llm_cached_tokens  AS cachedTokens,
       ae.llm_cost_usd       AS costUsd,
       ae.created_at         AS createdAt
ORDER BY ae.created_at DESC
LIMIT $limit
"""
)

# Full-period aggregate for totals -- no LIMIT so totals are never under-counted.
GET_AUDIT_EVENT_SPEND_TOTALS = (
    "MATCH (ae:AuditEvent) "
    + _AUDIT_EVENT_WHERE
    + """RETURN count(ae)                      AS runCount,
       sum(ae.llm_input_tokens)          AS inputTokens,
       sum(ae.llm_output_tokens)         AS outputTokens,
       sum(coalesce(ae.llm_cached_tokens, 0)) AS cachedTokens,
       sum(coalesce(ae.llm_cost_usd, 0)) AS costUsd
"""
)
