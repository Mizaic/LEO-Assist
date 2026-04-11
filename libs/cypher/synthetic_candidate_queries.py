"""Cypher queries for synthetic NER gold candidate generation."""

_NORMALISED_TAG = (
    "toLower("
    "replace("
    "replace("
    "replace(coalesce(c.semantic_tag, 'unknown'), ' ', '_'),"
    "'-', '_'),"
    "'/', '_')"
    ")"
)

GET_SURFACE_FORMS_FOR_GENERATION = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE coalesce(sf.status, 'active') = 'active'
  AND (
      $semantic_tags IS NULL
      OR size($semantic_tags) = 0
      OR """
GET_SURFACE_FORMS_FOR_GENERATION += _NORMALISED_TAG
GET_SURFACE_FORMS_FOR_GENERATION += """ IN $semantic_tags
  )
  AND NOT EXISTS {
      MATCH (g:GoldLabel)
      WHERE g.source = 'synthetic_llm'
        AND g.entities_json IS NOT NULL
        AND toLower(g.text) CONTAINS toLower(sf.form)
        AND g.entities_json CONTAINS toString(c.id)
  }
RETURN
    sf.form AS form,
    sf.normalized AS normalized,
    sf.source AS source,
    c.id AS concept_id,
    c.fsn AS preferred_term,
    """
GET_SURFACE_FORMS_FOR_GENERATION += _NORMALISED_TAG
GET_SURFACE_FORMS_FOR_GENERATION += """ AS semantic_tag
ORDER BY sf.form ASC
LIMIT $limit
"""

GET_SURFACE_FORM_TAG_COUNTS = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE coalesce(sf.status, 'active') = 'active'
RETURN
    """
GET_SURFACE_FORM_TAG_COUNTS += _NORMALISED_TAG
GET_SURFACE_FORM_TAG_COUNTS += """ AS semantic_tag,
    count(DISTINCT sf.form + '|' + toString(c.id)) AS total_surface_forms
ORDER BY total_surface_forms DESC
"""

GET_SYNTHETIC_GOLD_STATS = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WITH collect({form: sf.form, concept_id: toString(c.id)}) AS rows
WITH
    size(rows) AS total_surface_forms,
    [
        row IN rows
        WHERE EXISTS {
            MATCH (g:GoldLabel)
            WHERE g.source = 'synthetic_llm'
              AND g.entities_json IS NOT NULL
              AND toLower(g.text) CONTAINS toLower(row.form)
              AND g.entities_json CONTAINS row.concept_id
        }
    ] AS covered_rows
RETURN
    total_surface_forms,
    size(covered_rows) AS covered_surface_forms
"""

GET_SYNTHETIC_GOLD_TAG_BREAKDOWN = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WITH sf, c, """
GET_SYNTHETIC_GOLD_TAG_BREAKDOWN += _NORMALISED_TAG
GET_SYNTHETIC_GOLD_TAG_BREAKDOWN += """ AS semantic_tag
WITH sf, c, semantic_tag
WHERE EXISTS {
    MATCH (g:GoldLabel)
    WHERE g.source = 'synthetic_llm'
      AND g.entities_json IS NOT NULL
      AND toLower(g.text) CONTAINS toLower(sf.form)
      AND g.entities_json CONTAINS toString(c.id)
}
RETURN
    semantic_tag,
    count(DISTINCT sf.form + '|' + toString(c.id)) AS covered_surface_forms
ORDER BY covered_surface_forms DESC
"""

GET_ENCOUNTER_CONTEXT_CANDIDATES = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text IS NOT NULL
  AND trim(e.text) <> ''
  AND size(trim(e.text)) >= 250
WITH
    toString(p.id) AS patient_id,
    toString(e.id) AS encounter_id,
    toString(e.date) AS encounter_date,
    e.text AS encounter_text
WITH
    patient_id,
    encounter_id,
    encounter_date,
    substring(encounter_date, 0, 7) AS month_bucket,
    encounter_text
ORDER BY encounter_date DESC
LIMIT $limit
RETURN
    patient_id,
    encounter_id,
    encounter_date,
    month_bucket,
    encounter_text
"""
