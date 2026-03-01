"""Cypher queries for NER post-processor suppression/rewrite rules."""

# ------------------------------------------------------------------
# Write queries
# ------------------------------------------------------------------

UPSERT_POST_PROCESSOR_RULE = """
MERGE (r:LabelPostProcessorRule {rule_id: $rule_id})
ON CREATE SET r.created_at = datetime()
SET r.active          = $active,
    r.priority        = $priority,
    r.action          = $action,
    r.match_text      = $match_text,
    r.match_label     = $match_label,
    r.context_regex   = $context_regex,
    r.window_chars    = $window_chars,
    r.rewrite_text    = $rewrite_text,
    r.rewrite_label   = $rewrite_label,
    r.created_by      = coalesce(r.created_by, $created_by),
    r.notes           = $notes,
    r.updated_at      = datetime()
RETURN r.rule_id AS rule_id
"""

UPDATE_POST_PROCESSOR_RULE_ACTIVE = """
MATCH (r:LabelPostProcessorRule {rule_id: $rule_id})
SET r.active = $active,
    r.updated_at = datetime()
RETURN r.rule_id AS rule_id, r.active AS active
"""

# ------------------------------------------------------------------
# Read queries
# ------------------------------------------------------------------

GET_POST_PROCESSOR_RULES = """
MATCH (r:LabelPostProcessorRule)
RETURN
    r.rule_id AS rule_id,
    coalesce(r.active, true) AS active,
    coalesce(r.priority, 100) AS priority,
    r.action AS action,
    r.match_text AS match_text,
    r.match_label AS match_label,
    r.context_regex AS context_regex,
    coalesce(r.window_chars, 40) AS window_chars,
    r.rewrite_text AS rewrite_text,
    r.rewrite_label AS rewrite_label,
    r.created_by AS created_by,
    r.notes AS notes,
    toString(r.created_at) AS created_at,
    toString(r.updated_at) AS updated_at
ORDER BY coalesce(r.priority, 100) ASC, r.updated_at DESC
"""

GET_ACTIVE_POST_PROCESSOR_RULES = """
MATCH (r:LabelPostProcessorRule)
WHERE coalesce(r.active, true) = true
RETURN
    r.rule_id AS rule_id,
    coalesce(r.priority, 100) AS priority,
    r.action AS action,
    r.match_text AS match_text,
    r.match_label AS match_label,
    r.context_regex AS context_regex,
    coalesce(r.window_chars, 40) AS window_chars,
    r.rewrite_text AS rewrite_text,
    r.rewrite_label AS rewrite_label
ORDER BY coalesce(r.priority, 100) ASC
"""
