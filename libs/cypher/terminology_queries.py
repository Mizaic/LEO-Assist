"""Shared Cypher query templates for terminology operations."""

# Neo4j does not support parameterised variable-length path bounds.
DESCENDANTS_TEMPLATE = """
MATCH (ancestor:Concept {{id: $concept_id}})<-[:IS_A*1..{depth}]-(d:Concept)
WHERE d.active = true
  AND ($semantic_tag IS NULL OR d.semantic_tag = $semantic_tag)
RETURN DISTINCT
    d.id            AS snomed_concept_id,
    d.fsn           AS term,
    d.semantic_tag  AS semantic_tag
ORDER BY d.fsn
LIMIT $limit
"""
