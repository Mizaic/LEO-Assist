"""Cypher queries for platform pricing, margin config, and per-tenant discounts.

Data model
----------
PricingConfig (singleton, id='default')
    target_margin   : float   — e.g. 0.75 means 75% gross margin target
    updated_at      : datetime
    updated_by      : string

OrgDiscount
    discount_id     : uuid
    org_id          : string  — links to Organization.id
    description     : string
    rate            : float   — e.g. 0.20 = 20% off list price
    type            : 'promo' | 'contract'
    valid_from      : datetime
    valid_to        : datetime | null  — null = perpetual (life of contract)
    is_active       : bool
    created_by      : string
    created_at      : datetime
    updated_at      : datetime

Pricing formula
---------------
  list_price     = raw_cost / (1 - target_margin)
  discount_total = min(Σ active discount rates, 1.0)
  billable       = list_price × (1 - discount_total)
  margin_£       = list_price - raw_cost
"""

# ── PricingConfig ─────────────────────────────────────────────────────────────

UPSERT_PRICING_CONFIG = """
MERGE (p:PricingConfig {config_id: 'default'})
ON CREATE SET
  p.target_margin = $target_margin,
  p.updated_by    = $updated_by,
  p.created_at    = datetime(),
  p.updated_at    = datetime()
ON MATCH SET
  p.target_margin = $target_margin,
  p.updated_by    = $updated_by,
  p.updated_at    = datetime()
RETURN p.target_margin AS target_margin, p.updated_at AS updated_at
"""

GET_PRICING_CONFIG = """
MATCH (p:PricingConfig {config_id: 'default'})
RETURN p.target_margin AS target_margin,
       p.updated_by    AS updated_by,
       toString(p.updated_at) AS updated_at
"""

# ── OrgDiscount CRUD ──────────────────────────────────────────────────────────

CREATE_ORG_DISCOUNT = """
CREATE (d:OrgDiscount {
  discount_id  : $discount_id,
  org_id       : $org_id,
  description  : $description,
  rate         : $rate,
  type         : $type,
  valid_from   : datetime($valid_from),
  valid_to     : CASE WHEN $valid_to IS NULL THEN null ELSE datetime($valid_to) END,
  is_active    : true,
  created_by   : $created_by,
  created_at   : datetime(),
  updated_at   : datetime()
})
RETURN d.discount_id AS discount_id
"""

LIST_ORG_DISCOUNTS = """
MATCH (d:OrgDiscount {org_id: $org_id})
RETURN d.discount_id              AS discountId,
       d.org_id                   AS orgId,
       d.description              AS description,
       d.rate                     AS rate,
       d.type                     AS type,
       toString(d.valid_from)     AS validFrom,
       toString(d.valid_to)       AS validTo,
       d.is_active                AS isActive,
       d.created_by               AS createdBy,
       toString(d.created_at)     AS createdAt
ORDER BY d.created_at DESC
"""

DEACTIVATE_ORG_DISCOUNT = """
MATCH (d:OrgDiscount {discount_id: $discount_id})
SET d.is_active = false, d.updated_at = datetime()
RETURN d.discount_id AS discount_id
"""

DELETE_ORG_DISCOUNT = """
MATCH (d:OrgDiscount {discount_id: $discount_id})
DELETE d
RETURN count(*) AS deleted
"""

# Compute the sum of all currently active discount rates for an org.
GET_ACTIVE_DISCOUNT_RATE = """
MATCH (d:OrgDiscount {org_id: $org_id, is_active: true})
WHERE d.valid_from <= datetime()
  AND (d.valid_to IS NULL OR d.valid_to >= datetime())
RETURN coalesce(sum(d.rate), 0.0) AS total_discount_rate,
       collect({
         discountId:  d.discount_id,
         description: d.description,
         rate:        d.rate,
         type:        d.type,
         validTo:     toString(d.valid_to)
       }) AS active_discounts
"""

# ── Per-tenant spend (aggregated from Patient Graph AuditEvents) ──────────────
# NOTE: This query runs against the PATIENT GRAPH, not the Knowledge Graph.

ORG_SPEND_SUMMARY = """
MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(org)
MATCH (ae:AuditEvent {patient_id: p.id})
WHERE ae.type = 'PipelineRun'
  AND ae.llm_input_tokens IS NOT NULL
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
WITH org,
     count(ae)                           AS runCount,
     sum(toInteger(ae.llm_input_tokens)) AS inputTokens,
     sum(toInteger(ae.llm_output_tokens))AS outputTokens,
     sum(toInteger(ae.llm_cached_tokens))AS cachedTokens,
     sum(toFloat(ae.llm_cost_usd))       AS rawCostUsd
RETURN org.id   AS orgId,
       org.name AS orgName,
       runCount,
       inputTokens,
       outputTokens,
       cachedTokens,
       rawCostUsd
ORDER BY rawCostUsd DESC
"""

# Platform spend: AuditEvents NOT linked to any patient (training, verification, etc.)
PLATFORM_SPEND_SUMMARY = """
MATCH (ae:AuditEvent)
WHERE ae.type IN ['PipelineRun', 'TrainingRun', 'VerificationRun', 'GoldDatasetRun']
  AND ae.llm_input_tokens IS NOT NULL
  AND (ae.patient_id IS NULL OR ae.patient_id = '')
  AND ($from_date IS NULL OR ae.created_at >= datetime($from_date))
  AND ($to_date   IS NULL OR ae.created_at <= datetime($to_date))
RETURN ae.type                              AS eventType,
       count(ae)                            AS runCount,
       sum(toInteger(ae.llm_input_tokens))  AS inputTokens,
       sum(toInteger(ae.llm_output_tokens)) AS outputTokens,
       sum(toInteger(ae.llm_cached_tokens)) AS cachedTokens,
       sum(toFloat(ae.llm_cost_usd))        AS rawCostUsd
ORDER BY rawCostUsd DESC
"""
