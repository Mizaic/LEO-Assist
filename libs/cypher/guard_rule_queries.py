"""Generic Cypher queries for configurable NER guard rules.

Atlas trace:
  DO: DO-F20DE29D
  DI: DI-34712A9A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F20DE29D")

All guard families share the :NerGuardRule node label. The `family` property
distinguishes types (e.g. "scope_guard", "lab_value_guard"). Family-specific
fields are stored in `payload` (JSON string) so the generic schema does not
require a column per guard type.
"""

GET_ALL_RULES = """
MATCH (r:NerGuardRule)
WHERE coalesce(r.active, true) = true
RETURN
  r.rule_id            AS rule_id,
  r.family             AS family,
  r.org_id             AS org_id,
  r.plan_definition_id AS plan_definition_id,
  r.priority           AS priority,
  r.created_by         AS created_by,
  r.created_at         AS created_at,
  r.active             AS active,
  r.payload            AS payload
ORDER BY r.family, coalesce(r.priority, 10) DESC
"""

GET_RULE_HISTORY = """
MATCH (r:NerGuardRule {rule_id: $rule_id})-[:HAS_VERSION]->(v:RuleVersion)
RETURN
  v.version     AS version,
  v.changed_at  AS changed_at,
  v.changed_by  AS changed_by,
  v.payload     AS payload
ORDER BY v.version DESC
LIMIT 20
"""

GET_RULES_BY_FAMILY = """
MATCH (r:NerGuardRule {family: $family})
WHERE coalesce(r.active, true) = true
RETURN
  r.rule_id            AS rule_id,
  r.family             AS family,
  r.org_id             AS org_id,
  r.plan_definition_id AS plan_definition_id,
  r.priority           AS priority,
  r.created_by         AS created_by,
  r.created_at         AS created_at,
  r.active             AS active,
  r.payload            AS payload
ORDER BY coalesce(r.priority, 10) DESC
"""

UPSERT_RULE = """
MERGE (r:NerGuardRule {rule_id: $rule_id})
SET
  r.family              = $family,
  r.org_id              = $org_id,
  r.plan_definition_id  = $plan_definition_id,
  r.priority            = $priority,
  r.created_by          = $created_by,
  r.created_at          = $created_at,
  r.updated_by          = $updated_by,
  r.updated_at          = $updated_at,
  r.active              = true,
  r.payload             = $payload
RETURN r.rule_id AS rule_id
"""

DEACTIVATE_RULE = """
MATCH (r:NerGuardRule {rule_id: $rule_id})
SET r.active      = false,
    r.updated_at  = $updated_at,
    r.updated_by  = $updated_by
RETURN r.rule_id AS rule_id
"""

GET_RULE_BY_ID = """
MATCH (r:NerGuardRule {rule_id: $rule_id})
RETURN
  r.rule_id            AS rule_id,
  r.family             AS family,
  r.org_id             AS org_id,
  r.plan_definition_id AS plan_definition_id,
  r.priority           AS priority,
  r.created_by         AS created_by,
  r.created_at         AS created_at,
  r.active             AS active,
  r.payload            AS payload
"""
