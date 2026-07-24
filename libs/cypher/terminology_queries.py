"""Shared Cypher query templates for terminology operations.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")
"""

SEMANTIC_TAGS_QUERY = """
MATCH (c:Concept)
WHERE c.active = true AND c.semantic_tag IS NOT NULL AND c.semantic_tag <> ''
RETURN DISTINCT
  toLower(
    replace(
      replace(
        replace(trim(c.semantic_tag), ' ', '_'),
      '-', '_'),
    '/', '_')
  ) AS semantic_tag
ORDER BY semantic_tag
"""

# Neo4j does not support parameterised variable-length path bounds.
DESCENDANTS_TEMPLATE = """
MATCH (ancestor:Concept {{id: $concept_id}})<-[:IS_A*1..{depth}]-(d:Concept)
WHERE d.active = true
  AND (
    $semantic_tag IS NULL OR
    toLower(
      replace(
        replace(
          replace(trim(coalesce(d.semantic_tag, '')), ' ', '_'),
        '-', '_'),
      '/', '_')
    ) = $semantic_tag
  )
RETURN DISTINCT
    d.id            AS snomed_concept_id,
    d.fsn           AS term,
    toLower(
      replace(
        replace(
          replace(trim(coalesce(d.semantic_tag, '')), ' ', '_'),
        '-', '_'),
      '/', '_')
    ) AS semantic_tag
ORDER BY d.fsn
LIMIT $limit
"""

# Pre-filters candidate rules with a cheap substring CONTAINS before the
# caller parses/walks logicJson in Python -- avoids paying JSON-parse
# cost for the (usually large) majority of rules that never mention the
# term at all. Deliberately over-inclusive: CONTAINS on the raw JSON
# string can match a substring inside an unrelated field, so the Python
# walker still re-checks the exact concept term before counting a hit.
RULES_WITH_LOGIC_JSON_CONTAINING_TERM = """
MATCH (rule:AppropriatenessRule)
WHERE rule.logicJson IS NOT NULL
  AND toLower(rule.logicJson) CONTAINS toLower($term)
RETURN rule.id AS rule_id, rule.logicJson AS logic_json
LIMIT $scan_limit
"""

# Unfiltered variant for the periodic term-conflict audit, which needs
# every rule's concept criteria rather than only those matching one term.
ALL_RULES_WITH_LOGIC_JSON = """
MATCH (rule:AppropriatenessRule)
WHERE rule.logicJson IS NOT NULL
RETURN rule.id AS rule_id, rule.logicJson AS logic_json
"""
