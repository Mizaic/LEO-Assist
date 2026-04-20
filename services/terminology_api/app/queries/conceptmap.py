"""Cypher queries for ConceptMap CRUD against the Knowledge Graph.

Atlas trace:
  DO: DO-1373B71F
  DI: DI-17B5738E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-1373B71F")
"""

CONCEPTMAP_UPSERT = """
MERGE (c:ConceptMap {id: $conceptMapId})
SET c.rawJson   = $rawJson,
    c.url       = $url,
    c.name      = $name,
    c.title     = $title,
    c.status    = $status,
    c.version   = $version,
    c.sourceUri = $sourceUri,
    c.targetUri = $targetUri,
    c.isGlobal  = true,
    c.tenantId  = null
RETURN c.rawJson AS rawJson
"""

CONCEPTMAP_GET = """
MATCH (c:ConceptMap {id: $conceptMapId})
RETURN c.rawJson AS rawJson
LIMIT 1
"""

CONCEPTMAP_DELETE = """
MATCH (c:ConceptMap {id: $conceptMapId})
DETACH DELETE c
"""

CONCEPTMAP_SEARCH = """
MATCH (c:ConceptMap)
WHERE ($name IS NULL OR c.name CONTAINS $name)
  AND ($status IS NULL OR c.status = $status)
  AND ($url IS NULL OR c.url = $url)
RETURN c.rawJson AS rawJson
ORDER BY c.name
SKIP $offset
LIMIT $limit
"""

CONCEPTMAP_COUNT = """
MATCH (c:ConceptMap)
WHERE ($name IS NULL OR c.name CONTAINS $name)
  AND ($status IS NULL OR c.status = $status)
  AND ($url IS NULL OR c.url = $url)
RETURN count(c) AS total
"""
