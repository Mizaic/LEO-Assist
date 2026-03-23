"""Cypher queries for ReferenceRange CRUD and lookup.

ReferenceRange nodes live in the Patient Graph and support tenant overrides:
  - org_id = null: platform default
  - org_id = "<tenant-org-id>": tenant-specific override
"""

UPSERT_REFERENCE_RANGE = """
MERGE (r:ReferenceRange {range_id: $range_id})
ON CREATE SET
  r.created_at = datetime()
SET
  r.conceptId = $concept_id,
  r.preferred_term = $preferred_term,
  r.unit = $unit,
  r.sex = $sex,
  r.age_min = $age_min,
  r.age_max = $age_max,
  r.low = $low,
  r.high = $high,
  r.critical_low = $critical_low,
  r.critical_high = $critical_high,
  r.source = $source,
  r.org_id = $org_id,
  r.updated_by = $updated_by,
  r.updated_at = datetime()
RETURN r.range_id AS range_id
"""


GET_REFERENCE_RANGE_BY_ID = """
MATCH (r:ReferenceRange {range_id: $range_id})
RETURN r.range_id AS range_id,
       r.conceptId AS concept_id,
       r.preferred_term AS preferred_term,
       r.unit AS unit,
       r.sex AS sex,
       r.age_min AS age_min,
       r.age_max AS age_max,
       r.low AS low,
       r.high AS high,
       r.critical_low AS critical_low,
       r.critical_high AS critical_high,
       r.source AS source,
       r.org_id AS org_id,
       r.updated_by AS updated_by,
       toString(r.updated_at) AS updated_at,
       toString(r.created_at) AS created_at
"""


GET_REFERENCE_RANGES_FOR_CONCEPT = """
MATCH (r:ReferenceRange)
WHERE r.conceptId = $concept_id
  AND ($org_id IS NULL OR r.org_id = $org_id OR r.org_id IS NULL)
RETURN r.range_id AS range_id,
       r.conceptId AS concept_id,
       r.preferred_term AS preferred_term,
       r.unit AS unit,
       r.sex AS sex,
       r.age_min AS age_min,
       r.age_max AS age_max,
       r.low AS low,
       r.high AS high,
       r.critical_low AS critical_low,
       r.critical_high AS critical_high,
       r.source AS source,
       r.org_id AS org_id,
       r.updated_by AS updated_by,
       toString(r.updated_at) AS updated_at
ORDER BY CASE
           WHEN $org_id IS NOT NULL AND r.org_id = $org_id THEN 0
           WHEN r.org_id IS NULL THEN 1
           ELSE 2
         END,
         coalesce(r.sex, 'zz'),
         coalesce(r.age_min, -1) DESC
"""


LIST_REFERENCE_RANGES = """
MATCH (r:ReferenceRange)
WHERE (
  $org_id IS NULL
  OR ($include_platform = true AND (r.org_id = $org_id OR r.org_id IS NULL))
  OR ($include_platform = false AND r.org_id = $org_id)
)
AND ($concept_id IS NULL OR r.conceptId = $concept_id)
RETURN r.range_id AS range_id,
       r.conceptId AS concept_id,
       r.preferred_term AS preferred_term,
       r.unit AS unit,
       r.sex AS sex,
       r.age_min AS age_min,
       r.age_max AS age_max,
       r.low AS low,
       r.high AS high,
       r.critical_low AS critical_low,
       r.critical_high AS critical_high,
       r.source AS source,
       r.org_id AS org_id,
       r.updated_by AS updated_by,
       toString(r.updated_at) AS updated_at,
       toString(r.created_at) AS created_at
ORDER BY r.conceptId, coalesce(r.sex, 'all'), coalesce(r.age_min, -1), coalesce(r.org_id, '')
"""


DELETE_REFERENCE_RANGE = """
MATCH (r:ReferenceRange {range_id: $range_id})
DELETE r
RETURN count(*) AS deleted
"""
