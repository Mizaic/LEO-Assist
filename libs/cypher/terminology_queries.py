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
