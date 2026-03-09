"""Cypher queries for generic ServiceConfig nodes.

ServiceConfig stores operational runtime settings in the knowledge graph so
multiple API replicas can share the same control plane without restarts.
"""

CREATE_CONSTRAINT_SERVICE_CONFIG = """
CREATE CONSTRAINT service_config_key IF NOT EXISTS
FOR (s:ServiceConfig) REQUIRE s.key IS UNIQUE
"""

UPSERT_SERVICE_CONFIG = """
MERGE (s:ServiceConfig {key: $key})
ON CREATE SET
  s.category     = $category,
  s.display_name = $display_name,
  s.description  = $description,
  s.config_json  = $config_json,
  s.source       = $source,
  s.created_at   = datetime(),
  s.updated_at   = datetime()
ON MATCH SET
  s.category     = $category,
  s.display_name = $display_name,
  s.description  = $description,
  s.config_json  = $config_json,
  s.source       = $source,
  s.updated_at   = datetime()
RETURN s.key AS key
"""

GET_SERVICE_CONFIG = """
MATCH (s:ServiceConfig {key: $key})
RETURN s.key          AS key,
       s.category     AS category,
       s.display_name AS displayName,
       s.description  AS description,
       s.config_json  AS configJson,
       s.source       AS source,
       s.updated_at   AS updatedAt
"""

LIST_SERVICE_CONFIGS = """
MATCH (s:ServiceConfig)
RETURN s.key          AS key,
       s.category     AS category,
       s.display_name AS displayName,
       s.description  AS description,
       s.config_json  AS configJson,
       s.source       AS source,
       s.updated_at   AS updatedAt
ORDER BY s.category, s.key
"""
