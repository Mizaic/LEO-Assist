"""Cypher queries for ModelConfig nodes in the Knowledge Graph.

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

ModelConfig is the single source of truth for cost estimation and spend
reporting. Env vars are only used as a bootstrap when no nodes exist yet
(fresh instance or DR restore).
"""

COUNT_MODEL_CONFIGS = """
MATCH (m:ModelConfig) RETURN count(m) AS total
"""

CREATE_MODEL_CONFIG = """
CREATE (m:ModelConfig {
  key:                     $key,
  provider:                $provider,
  tier:                    $tier,
  display_name:            $display_name,
  model_id:                $model_id,
  cost_per_1m_input:       $cost_per_1m_input,
  cost_per_1m_cached:      $cost_per_1m_cached,
  cost_per_1m_cache_write: $cost_per_1m_cache_write,
  cost_per_1m_output:      $cost_per_1m_output,
  is_active:               $is_active,
  source:                  'user',
  created_at:              datetime(),
  updated_at:              datetime()
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
  m.provider                   = $provider,
  m.tier                       = $tier,
  m.display_name               = $display_name,
  m.model_id                   = $model_id,
  m.cost_per_1m_input          = $cost_per_1m_input,
  m.cost_per_1m_cached         = $cost_per_1m_cached,
  m.cost_per_1m_cache_write    = $cost_per_1m_cache_write,
  m.cost_per_1m_output         = $cost_per_1m_output,
  m.is_active                  = $is_active,
  m.source                     = 'seed',
  m.created_at                 = datetime(),
  m.updated_at                 = datetime()
ON MATCH SET
  m.display_name               = CASE WHEN m.source = 'seed' THEN $display_name ELSE m.display_name END,
  m.model_id                   = CASE WHEN m.source = 'seed' THEN $model_id ELSE m.model_id END,
  m.cost_per_1m_input          = CASE WHEN m.source = 'seed' THEN $cost_per_1m_input ELSE m.cost_per_1m_input END,
  m.cost_per_1m_cached         = CASE WHEN m.source = 'seed' THEN $cost_per_1m_cached ELSE m.cost_per_1m_cached END,
  m.cost_per_1m_cache_write    = CASE WHEN m.source = 'seed' THEN $cost_per_1m_cache_write ELSE m.cost_per_1m_cache_write END,
  m.cost_per_1m_output         = CASE WHEN m.source = 'seed' THEN $cost_per_1m_output ELSE m.cost_per_1m_output END,
  m.updated_at                 = datetime()
RETURN m.key AS key, m.source AS source
"""

LIST_MODEL_CONFIGS = """
MATCH (m:ModelConfig)
RETURN m.key                     AS key,
       m.provider                AS provider,
       m.tier                    AS tier,
       m.display_name            AS displayName,
       m.model_id                AS modelId,
       m.cost_per_1m_input       AS costPer1mInput,
       m.cost_per_1m_cached      AS costPer1mCachedInput,
       coalesce(m.cost_per_1m_cache_write, 0.0) AS costPer1mCacheWrite,
       m.cost_per_1m_output      AS costPer1mOutput,
       m.is_active               AS isActive,
       m.source                  AS source,
       m.updated_at              AS updatedAt
ORDER BY m.provider, m.tier
"""

GET_MODEL_CONFIG = """
MATCH (m:ModelConfig {key: $key})
RETURN m.key                     AS key,
       m.provider                AS provider,
       m.tier                    AS tier,
       m.display_name            AS displayName,
       m.model_id                AS modelId,
       m.cost_per_1m_input       AS costPer1mInput,
       m.cost_per_1m_cached      AS costPer1mCachedInput,
       coalesce(m.cost_per_1m_cache_write, 0.0) AS costPer1mCacheWrite,
       m.cost_per_1m_output      AS costPer1mOutput,
       m.is_active               AS isActive,
       m.source                  AS source,
       m.updated_at              AS updatedAt
"""

UPDATE_MODEL_CONFIG = """
MATCH (m:ModelConfig {key: $key})
SET m.display_name             = $display_name,
    m.model_id                 = $model_id,
    m.cost_per_1m_input        = $cost_per_1m_input,
    m.cost_per_1m_cached       = $cost_per_1m_cached,
    m.cost_per_1m_cache_write  = $cost_per_1m_cache_write,
    m.cost_per_1m_output       = $cost_per_1m_output,
    m.is_active                = $is_active,
    m.source                   = 'user',
    m.updated_at               = datetime()
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
       c.llm_usage_json        AS llmUsageJson,
       'coding_extraction'     AS source
UNION
// DI-LEO-AI-506: include SBAR Assessment rows so the per-patient
// LLM spend drill-down covers every LLM-backed pipeline. The shape
// matches the EncounterCandidate row above so the API/UI need no
// change; the `source` discriminator lets the UI optionally label
// SBAR rows differently.
MATCH (p:Patient {id: $patient_id})-[:HAS_ASSESSMENT]->(a:Assessment)
WHERE a.llm_usage_json IS NOT NULL
  AND ($from_date IS NULL OR a.updated_at >= datetime($from_date))
  AND ($to_date   IS NULL OR a.updated_at <= datetime($to_date))
OPTIONAL MATCH (e:Encounter)-[:HAS_ASSESSMENT]->(a)
RETURN a.id                    AS candidateId,
       coalesce(e.id, '')      AS encounterId,
       a.updated_at            AS updatedAt,
       a.llm_model_id          AS modelName,
       a.llm_usage_json        AS llmUsageJson,
       'sbar_assessment'       AS source
UNION
// DI-LEO-AI-517: include episode-engine PipelineRun :AuditEvent rows so
// the per-patient drill-down covers Haiku/Sonnet runs that drive
// :EpisodeOfCare derivation. Spend is denormalised onto the AuditEvent
// already; we synthesise an llm_usage_json blob in the same shape the
// EncounterCandidate / Assessment branches emit so the API/UI parsing
// stays unchanged.
MATCH (ae:AuditEvent {type: 'PipelineRun'})
WHERE ae.subtype = 'episode_engine'
  AND ae.patient_id = $patient_id
  AND ae.llm_input_tokens IS NOT NULL
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
RETURN ae.run_id               AS candidateId,
       ''                      AS encounterId,
       ae.created_at           AS updatedAt,
       coalesce(ae.extraction_model_tier, 'small') AS modelName,
       apoc.convert.toJson({
         input_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)),
         output_tokens: toInteger(coalesce(ae.llm_output_tokens, 0)),
         cached_input_tokens: toInteger(coalesce(ae.llm_cached_tokens, 0)),
         total_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)) +
                        toInteger(coalesce(ae.llm_output_tokens, 0)),
         llm_calls:     toInteger(coalesce(ae.step_count, 0)),
         cost_usd:      toFloat(coalesce(ae.llm_cost_usd, 0))
       })                      AS llmUsageJson,
       'episode_engine'        AS source
UNION
// DI-LEO-AI-518: include guidance PipelineRun :AuditEvent rows whose
// patient_id was set (per-patient guidance dry-run from the rule editor).
// Platform-spend rows (patient_id IS NULL) are excluded by the join.
MATCH (ae:AuditEvent {type: 'PipelineRun'})
WHERE ae.subtype IN ['guidance_rule_extraction', 'guidance_rule_dry_run']
  AND ae.patient_id = $patient_id
  AND ae.llm_input_tokens IS NOT NULL
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
RETURN ae.run_id               AS candidateId,
       ''                      AS encounterId,
       ae.created_at           AS updatedAt,
       coalesce(ae.extraction_model_tier, 'small') AS modelName,
       apoc.convert.toJson({
         input_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)),
         output_tokens: toInteger(coalesce(ae.llm_output_tokens, 0)),
         cached_input_tokens: toInteger(coalesce(ae.llm_cached_tokens, 0)),
         total_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)) +
                        toInteger(coalesce(ae.llm_output_tokens, 0)),
         llm_calls:     toInteger(coalesce(ae.step_count, 0)),
         cost_usd:      toFloat(coalesce(ae.llm_cost_usd, 0))
       })                      AS llmUsageJson,
       coalesce(ae.subtype, 'guidance')  AS source
UNION
// 2026-07 CTO peer-review item 3 (Phase A): include the general coding
// PipelineRun :AuditEvent rows written by WorkflowEngine._write_audit_event
// (libs/workflow/engine.py) -- these runs power /pricing/orgs and
// /analytics/llm-spend/runs today (via GET_AUDIT_EVENT_SPEND / the
// AuditEvent-generic ORG_SPEND_SUMMARY query) but were never visible in
// the per-patient drill-down. WorkflowEngine writes no `subtype`, so we
// exclude subtypes already carried by the two arms above to guarantee
// this arm cannot double-count episode-engine or guidance rows.
MATCH (ae:AuditEvent {type: 'PipelineRun'})
WHERE (ae.subtype IS NULL OR ae.subtype NOT IN
        ['episode_engine', 'guidance_rule_extraction', 'guidance_rule_dry_run'])
  AND ae.patient_id = $patient_id
  AND ae.llm_input_tokens IS NOT NULL
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
RETURN ae.run_id               AS candidateId,
       coalesce(ae.encounter_id, '') AS encounterId,
       ae.created_at           AS updatedAt,
       coalesce(ae.extraction_model_tier, 'small') AS modelName,
       apoc.convert.toJson({
         input_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)),
         output_tokens: toInteger(coalesce(ae.llm_output_tokens, 0)),
         cached_input_tokens: toInteger(coalesce(ae.llm_cached_tokens, 0)),
         total_tokens:  toInteger(coalesce(ae.llm_input_tokens, 0)) +
                        toInteger(coalesce(ae.llm_output_tokens, 0)),
         llm_calls:     toInteger(coalesce(ae.step_count, 0)),
         cost_usd:      toFloat(coalesce(ae.llm_cost_usd, 0))
       })                      AS llmUsageJson,
       'coding_pipeline_run'   AS source
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
  AND (
    ($selected_org_id IS NOT NULL AND EXISTS {
      MATCH (ae_p:Patient {id: ae.patient_id})-[:HAS_GENERAL_PRACTITIONER]->(ae_gp)
      WHERE ae_gp.id = $selected_org_id
    })
    OR
    ($selected_org_id IS NULL AND (
      $is_admin = true
      OR EXISTS {
        MATCH (ae_p:Patient {id: ae.patient_id})-[:HAS_GENERAL_PRACTITIONER]->(ae_gp)
        WHERE ae_gp.id IN $org_ids
      }
    ))
  )
"""

GET_AUDIT_EVENT_SPEND = (
    "MATCH (ae:AuditEvent) "
    + _AUDIT_EVENT_WHERE
    + """RETURN ae.run_id                    AS runId,
       ae.patient_id                 AS patientId,
       ae.encounter_id               AS encounterId,
       ae.status                     AS status,
       ae.step_count                 AS stepCount,
       ae.entity_count               AS entityCount,
       ae.error_count                AS errorCount,
       ae.first_error                AS firstError,
       ae.total_duration_ms          AS durationMs,
       ae.llm_input_tokens           AS inputTokens,
       ae.llm_output_tokens          AS outputTokens,
       ae.llm_cached_tokens          AS cachedTokens,
       ae.llm_cost_usd               AS costUsd,
       ae.extraction_prompt_name     AS extractionPromptName,
       ae.extraction_prompt_version  AS extractionPromptVersion,
       ae.extraction_prompt_hash     AS extractionPromptHash,
       ae.extraction_provider        AS extractionProvider,
       ae.extraction_model_tier      AS extractionModelTier,
       ae.created_at                 AS createdAt
ORDER BY ae.created_at DESC
LIMIT $limit
"""
)

# Full-period aggregate for totals -- no LIMIT so totals are never under-counted.
GET_AUDIT_EVENT_SPEND_TOTALS = (
    "MATCH (ae:AuditEvent) "
    + _AUDIT_EVENT_WHERE
    + """RETURN count(ae)                           AS runCount,
       sum(ae.llm_input_tokens)               AS inputTokens,
       sum(ae.llm_output_tokens)              AS outputTokens,
       sum(coalesce(ae.llm_cached_tokens, 0)) AS cachedTokens,
       sum(coalesce(ae.llm_cost_usd, 0))      AS costUsd
"""
)

# ---------------------------------------------------------------------------
# Quality regression: empty-extraction rate by prompt version
#
# Returns one row per (prompt_name, prompt_version, prompt_hash) tuple with
# run totals and the rate of empty_extraction outcomes.  Used by quality gates
# and the /analytics/llm-spend/prompt-quality endpoint.
# ---------------------------------------------------------------------------
GET_AUDIT_EMPTY_RATE_BY_PROMPT = """
MATCH (ae:AuditEvent)
WHERE ae.type = 'PipelineRun'
  AND ae.extraction_prompt_name IS NOT NULL
  AND ae.extraction_prompt_name <> ''
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
WITH ae.extraction_prompt_name    AS promptName,
     ae.extraction_prompt_version AS promptVersion,
     ae.extraction_prompt_hash    AS promptHash,
     count(ae)                    AS totalRuns,
     sum(CASE WHEN ae.status = 'empty_extraction' THEN 1 ELSE 0 END) AS emptyRuns,
     sum(CASE WHEN ae.status = 'error'            THEN 1 ELSE 0 END) AS errorRuns,
     avg(toFloat(ae.entity_count))                                    AS avgEntityCount,
     avg(toFloat(ae.total_duration_ms))                               AS avgDurationMs,
     sum(coalesce(ae.llm_cost_usd, 0))                                AS totalCostUsd
RETURN promptName,
       promptVersion,
       promptHash,
       totalRuns,
       emptyRuns,
       errorRuns,
       round(toFloat(emptyRuns) / CASE WHEN totalRuns > 0 THEN totalRuns ELSE 1 END, 4) AS emptyRate,
       round(avgEntityCount, 2)   AS avgEntityCount,
       round(avgDurationMs, 0)    AS avgDurationMs,
       round(totalCostUsd, 4)     AS totalCostUsd
ORDER BY promptVersion DESC, totalRuns DESC
"""

# ---------------------------------------------------------------------------
# Quality regression: per-provider cost and entity yield comparison
#
# Answers: "Does AWS produce more codes per dollar than Azure for this period?"
# ---------------------------------------------------------------------------
GET_AUDIT_PROVIDER_COMPARISON = """
MATCH (ae:AuditEvent)
WHERE ae.type = 'PipelineRun'
  AND ae.extraction_provider IS NOT NULL
  AND ae.extraction_provider <> ''
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
WITH ae.extraction_provider    AS provider,
     ae.extraction_model_tier  AS modelTier,
     count(ae)                 AS runCount,
     sum(CASE WHEN ae.status = 'empty_extraction' THEN 1 ELSE 0 END) AS emptyRuns,
     avg(toFloat(ae.entity_count))               AS avgEntityCount,
     avg(toFloat(ae.total_duration_ms))           AS avgDurationMs,
     sum(coalesce(ae.llm_cost_usd, 0))            AS totalCostUsd,
     sum(toInteger(ae.llm_input_tokens))          AS totalInputTokens,
     sum(toInteger(ae.llm_output_tokens))         AS totalOutputTokens
RETURN provider,
       modelTier,
       runCount,
       emptyRuns,
       round(toFloat(emptyRuns) / CASE WHEN runCount > 0 THEN runCount ELSE 1 END, 4) AS emptyRate,
       round(avgEntityCount, 2)  AS avgEntityCount,
       round(avgDurationMs, 0)   AS avgDurationMs,
       round(totalCostUsd, 4)    AS totalCostUsd,
       totalInputTokens,
       totalOutputTokens
ORDER BY totalCostUsd DESC
"""

# ---------------------------------------------------------------------------
# Recent pipeline errors grouped by first_error pattern
#
# Enables: "What error types have spiked in the last 24 hours?"
# ---------------------------------------------------------------------------
GET_AUDIT_RECENT_ERRORS = """
MATCH (ae:AuditEvent)
WHERE ae.type = 'PipelineRun'
  AND ae.error_count > 0
  AND ae.first_error IS NOT NULL
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
RETURN ae.first_error AS firstError,
       count(ae)      AS occurrences,
       max(ae.created_at) AS lastSeen
ORDER BY occurrences DESC
LIMIT $limit
"""
