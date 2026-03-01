"""Cypher queries for ValueSet CRUD against the Knowledge Graph."""

VALUESET_UPSERT = """
MERGE (v:ValueSet {id: $valueSetId})
SET v.rawJson   = $rawJson,
    v.url       = $url,
    v.name      = $name,
    v.title     = $title,
    v.status    = $status,
    v.version   = $version,
    v.isGlobal  = true,
    v.tenantId  = null
RETURN v.rawJson AS rawJson
"""

VALUESET_GET = """
MATCH (v:ValueSet {id: $valueSetId})
RETURN v.rawJson AS rawJson
LIMIT 1
"""

VALUESET_GET_BY_URL = """
MATCH (v:ValueSet {url: $url})
RETURN v.rawJson AS rawJson
ORDER BY v.version DESC
LIMIT 1
"""

VALUESET_DELETE = """
MATCH (v:ValueSet {id: $valueSetId})
DETACH DELETE v
"""

VALUESET_SEARCH = """
MATCH (v:ValueSet)
WHERE ($name IS NULL OR v.name CONTAINS $name)
  AND ($status IS NULL OR v.status = $status)
  AND ($url IS NULL OR v.url = $url)
RETURN v.rawJson AS rawJson
ORDER BY v.name
SKIP $offset
LIMIT $limit
"""

VALUESET_COUNT = """
MATCH (v:ValueSet)
WHERE ($name IS NULL OR v.name CONTAINS $name)
  AND ($status IS NULL OR v.status = $status)
  AND ($url IS NULL OR v.url = $url)
RETURN count(v) AS total
"""
