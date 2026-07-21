"""Create / list / deactivate LEO-local Concept nodes.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libs.terminology.local_concepts import (
    CODE_SYSTEM_LEO_LOCAL,
    RESERVED_ACTION_TEMPLATES,
    slugify_local_label,
    validate_concept_kind,
    validate_local_concept_id,
)

CREATE_LOCAL_CONCEPT = """
MERGE (c:Concept {id: $id})
ON CREATE SET
  c.fsn = $fsn,
  c.preferred_term = $preferred_term,
  c.semantic_tag = $semantic_tag,
  c.code_system = $code_system,
  c.concept_kind = $concept_kind,
  c.is_local = true,
  c.active = true,
  c.created_at = datetime($created_at),
  c.created_by = $created_by,
  c.description = $description
ON MATCH SET
  c.fsn = $fsn,
  c.preferred_term = $preferred_term,
  c.semantic_tag = $semantic_tag,
  c.concept_kind = $concept_kind,
  c.code_system = $code_system,
  c.is_local = true,
  c.active = true,
  c.updated_at = datetime($created_at),
  c.updated_by = $created_by,
  c.description = coalesce($description, c.description)
RETURN c.id AS id,
       c.fsn AS fsn,
       c.preferred_term AS preferred_term,
       c.semantic_tag AS semantic_tag,
       c.code_system AS code_system,
       c.concept_kind AS concept_kind,
       c.is_local AS is_local,
       c.active AS active,
       c.description AS description
"""

ENSURE_LOCAL_TERM = """
MERGE (t:Term {normalized_form: $term_normalized})
ON CREATE SET
  t.id = $term_id,
  t.term = $preferred_term,
  t.type = 'FSN',
  t.active = true
WITH t
MATCH (c:Concept {id: $id})
MERGE (t)-[:DESCRIBES]->(c)
RETURN t.normalized_form AS normalized_form
"""

GET_LOCAL_CONCEPT = """
MATCH (c:Concept {id: $id})
WHERE coalesce(c.is_local, false) = true
   OR coalesce(c.code_system, '') = $code_system
RETURN c.id AS id,
       c.fsn AS fsn,
       c.preferred_term AS preferred_term,
       c.semantic_tag AS semantic_tag,
       c.code_system AS code_system,
       c.concept_kind AS concept_kind,
       c.is_local AS is_local,
       c.active AS active,
       c.description AS description
"""

LIST_LOCAL_CONCEPTS = """
MATCH (c:Concept)
WHERE coalesce(c.is_local, false) = true
   OR coalesce(c.code_system, '') = $code_system
RETURN c.id AS id,
       c.fsn AS fsn,
       c.preferred_term AS preferred_term,
       c.semantic_tag AS semantic_tag,
       c.code_system AS code_system,
       c.concept_kind AS concept_kind,
       c.is_local AS is_local,
       c.active AS active,
       c.description AS description
ORDER BY c.id
SKIP $offset
LIMIT $limit
"""

COUNT_LOCAL_CONCEPTS = """
MATCH (c:Concept)
WHERE coalesce(c.is_local, false) = true
   OR coalesce(c.code_system, '') = $code_system
RETURN count(c) AS total
"""

DEACTIVATE_LOCAL_CONCEPT = """
MATCH (c:Concept {id: $id})
WHERE coalesce(c.is_local, false) = true
   OR coalesce(c.code_system, '') = $code_system
SET c.active = false,
    c.updated_at = datetime($updated_at),
    c.updated_by = $updated_by
RETURN c.id AS id, c.active AS active
"""

ENSURE_ACTION_TEMPLATE = """
MERGE (c:Concept {id: $id})
ON CREATE SET
  c.fsn = $fsn,
  c.preferred_term = $fsn,
  c.semantic_tag = 'narrative_action',
  c.code_system = $code_system,
  c.concept_kind = 'narrative_action',
  c.is_local = true,
  c.active = true,
  c.created_at = datetime($created_at),
  c.created_by = 'system'
ON MATCH SET
  c.code_system = $code_system,
  c.is_local = true,
  c.active = true,
  c.concept_kind = 'narrative_action'
RETURN c.id AS id, c.fsn AS fsn, c.concept_kind AS concept_kind
"""

CONFLICTING_SNOMED = """
MATCH (c:Concept {id: $id})
WHERE coalesce(c.is_local, false) = false
  AND coalesce(c.code_system, 'snomed') <> $code_system
RETURN c.id AS id, c.fsn AS fsn LIMIT 1
"""


def build_create_params(
    *,
    concept_id: str | None,
    display_name: str,
    concept_kind: str,
    description: str | None,
    created_by: str,
    semantic_tag: str | None = None,
) -> dict[str, Any]:
    """Validate inputs and build Cypher params for create."""
    kind = validate_concept_kind(concept_kind)
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name is required.")
    if concept_id:
        cid = validate_local_concept_id(concept_id)
    else:
        prefix = "LEO-ACT" if kind == "narrative_action" else "LEO-LOCAL"
        cid = slugify_local_label(name, prefix=prefix)
    fsn_suffix = " (LEO local)"
    fsn = name if name.endswith(fsn_suffix) else f"{name}{fsn_suffix}"
    preferred = name
    tag = (semantic_tag or kind).strip() or kind
    term_normalized = preferred.lower().strip()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": cid,
        "fsn": fsn,
        "preferred_term": preferred,
        "semantic_tag": tag,
        "code_system": CODE_SYSTEM_LEO_LOCAL,
        "concept_kind": kind,
        "created_at": now,
        "created_by": created_by or "system",
        "term_normalized": term_normalized,
        "term_id": f"term:{cid}",
        "description": (description or "").strip() or None,
    }


def seed_reserved_action_params() -> list[dict[str, Any]]:
    """Return Cypher params for reserved LEO-ACT-* templates."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": cid,
            "fsn": fsn,
            "code_system": CODE_SYSTEM_LEO_LOCAL,
            "created_at": now,
        }
        for cid, fsn in RESERVED_ACTION_TEMPLATES.items()
    ]
