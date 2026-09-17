"""Cypher for spend true-up, quotas, and the monthly pack.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

SUM_OUR_LLM_SPEND = """
MATCH (ae:AuditEvent)
WHERE ae.type = 'PipelineRun'
  AND ae.created_at >= datetime($from_date)
  AND ae.created_at < datetime($to_date)
RETURN coalesce(sum(toInteger(ae.llm_input_tokens)), 0) AS input_tokens,
       coalesce(sum(toInteger(ae.llm_output_tokens)), 0) AS output_tokens,
       coalesce(sum(toInteger(ae.llm_cached_tokens)), 0) AS cached_tokens,
       coalesce(sum(toFloat(ae.llm_cost_usd)), 0.0) AS cost_usd
"""

LIST_AUDIT_EVENT_IDS = """
MATCH (ae:AuditEvent)
WHERE ae.type = 'PipelineRun'
  AND ae.created_at >= datetime($from_date)
  AND ae.created_at < datetime($to_date)
RETURN ae.id AS id
LIMIT 20
"""

UPSERT_TRUE_UP = """
MERGE (t:LlmSpendTrueUp {date: $date, environment: $environment})
ON CREATE SET t.created_at = datetime()
SET t.our_input_tokens = $our_input_tokens,
    t.our_output_tokens = $our_output_tokens,
    t.our_cached_tokens = $our_cached_tokens,
    t.our_cost_usd = $our_cost_usd,
    t.azure_prompt_tokens = $azure_prompt_tokens,
    t.azure_completion_tokens = $azure_completion_tokens,
    t.azure_cost_gbp = $azure_cost_gbp,
    t.azure_cost_usd = $azure_cost_usd,
    t.token_drift = $token_drift,
    t.cost_drift = $cost_drift,
    t.cost_provisional = $cost_provisional,
    t.status = $status,
    t.azure_scope = 'account-wide',
    t.updated_at = datetime()
RETURN t.date AS date
"""

GET_LATEST_TRUE_UP = """
MATCH (t:LlmSpendTrueUp {environment: $environment})
RETURN t.date AS date,
       t.our_input_tokens AS ourInputTokens,
       t.our_output_tokens AS ourOutputTokens,
       t.our_cached_tokens AS ourCachedTokens,
       t.our_cost_usd AS ourCostUsd,
       t.azure_prompt_tokens AS azurePromptTokens,
       t.azure_completion_tokens AS azureCompletionTokens,
       t.azure_cost_gbp AS azureCostGbp,
       t.azure_cost_usd AS azureCostUsd,
       t.token_drift AS tokenDrift,
       t.cost_drift AS costDrift,
       t.cost_provisional AS costProvisional,
       t.status AS status,
       t.azure_scope AS azureScope
ORDER BY t.date DESC
LIMIT 1
"""

GET_TRUE_UP_FOR_MONTH = """
MATCH (t:LlmSpendTrueUp {environment: $environment})
WHERE t.date >= $month_start AND t.date < $month_end
  AND t.azure_cost_gbp IS NOT NULL
RETURN coalesce(sum(toFloat(t.azure_cost_gbp)), 0.0) AS azure_cost_gbp
"""

UPSERT_ENCOUNTER_QUOTA = """
MERGE (q:OrgEncounterQuota {org_id: $org_id})
ON CREATE SET q.created_at = datetime()
SET q.monthly_limit = $monthly_limit,
    q.updated_at = datetime(),
    q.org_name = $org_name
RETURN q.org_id AS orgId, q.monthly_limit AS monthlyLimit, q.org_name AS orgName
"""

LIST_ENCOUNTER_QUOTAS = """
MATCH (q:OrgEncounterQuota)
WHERE q.monthly_limit IS NOT NULL AND q.monthly_limit > 0
RETURN q.org_id AS orgId, q.monthly_limit AS monthlyLimit, q.org_name AS orgName
"""

COUNT_ENCOUNTERS_BY_ORG = """
MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(org)
MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(e.created_at, e.period_start) >= datetime($from_date)
  AND coalesce(e.created_at, e.period_start) < datetime($to_date)
RETURN org.id AS orgId,
       coalesce(org.name, org.id) AS orgName,
       count(e) AS encounters
"""

ORG_RAW_SPEND = """
MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(org)
MATCH (ae:AuditEvent {patient_id: p.id})
WHERE ae.type = 'PipelineRun'
  AND ae.llm_input_tokens IS NOT NULL
  AND ae.created_at >= datetime($from_date)
  AND ae.created_at < datetime($to_date)
RETURN org.id AS orgId,
       coalesce(org.name, org.id) AS orgName,
       count(ae) AS runCount,
       coalesce(sum(toInteger(ae.llm_input_tokens)), 0) AS inputTokens,
       coalesce(sum(toInteger(ae.llm_output_tokens)), 0) AS outputTokens,
       coalesce(sum(toFloat(ae.llm_cost_usd)), 0.0) AS ourCostUsd
"""

GET_MONTHLY_PACK = """
MATCH (p:LlmSpendMonthlyPack {month: $month, environment: $environment})
RETURN p.month AS month, p.sent_at AS sentAt
"""

MARK_MONTHLY_PACK_SENT = """
MERGE (p:LlmSpendMonthlyPack {month: $month, environment: $environment})
ON CREATE SET p.created_at = datetime()
SET p.sent_at = datetime()
RETURN p.month AS month
"""
