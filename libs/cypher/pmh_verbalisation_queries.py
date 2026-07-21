"""Knowledge-graph Cypher for PMH narrative verbalisation."""

from __future__ import annotations

FSN_TYPE_ID = "900000000000003001"

LIST_SURFACE_FORMS_FOR_CONCEPTS = """
UNWIND $concept_ids AS cid
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE toString(c.id) = toString(cid)
  AND coalesce(sf.status, 'active') IN ['active', 'approved']
  AND trim(coalesce(sf.form, '')) <> ''
RETURN toString(c.id) AS concept_id,
       collect(DISTINCT sf.form) AS forms
"""

LIST_TERM_SYNONYMS_FOR_CONCEPTS = """
UNWIND $concept_ids AS cid
MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE toString(c.id) = toString(cid)
  AND coalesce(t.active, true) = true
  AND coalesce(t.term_type, '') <> $fsn_type_id
  AND trim(coalesce(t.surface_form, '')) <> ''
RETURN toString(c.id) AS concept_id,
       collect(DISTINCT t.surface_form) AS forms
"""

LIST_PREFERRED_TERMS_FOR_CONCEPTS = """
UNWIND $concept_ids AS cid
MATCH (c:Concept)
WHERE toString(c.id) = toString(cid)
RETURN toString(c.id) AS concept_id,
       coalesce(c.preferred_term, c.term, c.fsn, '') AS term
"""
