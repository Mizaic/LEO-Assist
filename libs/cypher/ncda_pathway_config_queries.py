"""Cypher queries for NCDAPathwayConfig CRUD.

Storage: one (:NCDAPathwayConfig {site_key}) node per cancer site, with
the typical-time bands (in days) as properties. Tracked-history pattern
adds updated_by and updated_at on each upsert.
"""

UPSERT_NCDA_PATHWAY_CONFIG = """
MERGE (c:NCDAPathwayConfig {site_key: $site_key})
ON CREATE SET c.created_at = datetime()
SET
  c.ftr_to_seen_typical_max_days = $ftr_to_seen_typical_max_days,
  c.seen_to_dx_typical_max_days = $seen_to_dx_typical_max_days,
  c.dx_to_treatment_typical_max_days = $dx_to_treatment_typical_max_days,
  c.ftr_to_dx_typical_max_days = $ftr_to_dx_typical_max_days,
  c.ftr_to_treatment_typical_max_days = $ftr_to_treatment_typical_max_days,
  c.updated_by = $updated_by,
  c.updated_at = datetime()
RETURN c.site_key AS site_key
"""


LIST_NCDA_PATHWAY_CONFIG = """
MATCH (c:NCDAPathwayConfig)
RETURN c.site_key AS site_key,
       c.ftr_to_seen_typical_max_days AS ftr_to_seen_typical_max_days,
       c.seen_to_dx_typical_max_days AS seen_to_dx_typical_max_days,
       c.dx_to_treatment_typical_max_days AS dx_to_treatment_typical_max_days,
       c.ftr_to_dx_typical_max_days AS ftr_to_dx_typical_max_days,
       c.ftr_to_treatment_typical_max_days AS ftr_to_treatment_typical_max_days,
       c.updated_by AS updated_by,
       toString(c.updated_at) AS updated_at
ORDER BY c.site_key
"""


GET_NCDA_PATHWAY_CONFIG = """
MATCH (c:NCDAPathwayConfig {site_key: $site_key})
RETURN c.site_key AS site_key,
       c.ftr_to_seen_typical_max_days AS ftr_to_seen_typical_max_days,
       c.seen_to_dx_typical_max_days AS seen_to_dx_typical_max_days,
       c.dx_to_treatment_typical_max_days AS dx_to_treatment_typical_max_days,
       c.ftr_to_dx_typical_max_days AS ftr_to_dx_typical_max_days,
       c.ftr_to_treatment_typical_max_days AS ftr_to_treatment_typical_max_days,
       c.updated_by AS updated_by,
       toString(c.updated_at) AS updated_at
"""
