"""Exact-match recovery of approved LEO-local concept aliases from clinical text.

Loaded patterns come from Neo4j SurfaceForm -> local Concept mappings
(status approved/active). Fail-closed: empty pattern list is a no-op.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from libs.terminology.local_concepts import CODE_SYSTEM_LEO_LOCAL

_RECOVERY_MARKER = "_recovered_local_concept"


@dataclass(frozen=True)
class LocalConceptPattern:
    normalized: str
    form: str
    concept_id: str
    fsn: str
    semantic_tag: str = "finding"


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def compile_pattern(form: str) -> re.Pattern[str] | None:
    """Build a word-boundary regex for an alias form."""
    phrase = _norm(form)
    if not phrase:
        return None
    parts = [re.escape(p) for p in phrase.split()]
    if not parts:
        return None
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)


def recover_local_concept_entities(
    text: str,
    entities: list[dict[str, Any]],
    patterns: Iterable[LocalConceptPattern],
) -> list[dict[str, Any]]:
    """Append recovered local-concept entities that are not already present.

    Happy path: matching phrase adds an entity with local concept_id.
    Non-happy: blank text, no patterns, or already-covered spans are skipped.
    """
    source = text or ""
    if not source.strip():
        return list(entities)

    existing_ids = {
        str(e.get("snomed_concept_id") or e.get("concept_id") or "")
        for e in entities
        if isinstance(e, dict)
    }
    existing_norms = {
        _norm(str(e.get("text") or e.get("lookup_term") or ""))
        for e in entities
        if isinstance(e, dict)
    }

    out = list(entities)
    for pattern in patterns:
        if not pattern.concept_id.startswith("LEO-"):
            continue
        rx = compile_pattern(pattern.form or pattern.normalized)
        if rx is None:
            continue
        if pattern.concept_id in existing_ids:
            continue
        if _norm(pattern.form) in existing_norms:
            continue
        match = rx.search(source)
        if not match:
            continue
        out.append(
            {
                "text": match.group(0),
                "lookup_term": pattern.form or pattern.normalized,
                "start": match.start(),
                "end": match.end(),
                "label": pattern.semantic_tag or "finding",
                "semantic_tag": pattern.semantic_tag or "finding",
                "assertion": "present",
                "snomed_concept_id": pattern.concept_id,
                "concept_id": pattern.concept_id,
                "snomed_term": pattern.fsn,
                "code_system": CODE_SYSTEM_LEO_LOCAL,
                "is_local": True,
                _RECOVERY_MARKER: True,
                "confidence": 0.95,
            }
        )
        existing_ids.add(pattern.concept_id)
        existing_norms.add(_norm(pattern.form))
    return out


FETCH_APPROVED_LOCAL_PATTERNS = """
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
WHERE coalesce(c.is_local, false) = true
  AND coalesce(c.code_system, '') = $code_system
  AND c.active = true
  AND coalesce(sf.status, 'approved') IN ['approved', 'active']
RETURN sf.normalized AS normalized,
       sf.form AS form,
       c.id AS concept_id,
       coalesce(c.fsn, c.preferred_term, c.id) AS fsn,
       coalesce(c.semantic_tag, c.concept_kind, 'finding') AS semantic_tag
"""


def patterns_from_rows(rows: list[dict[str, Any]]) -> list[LocalConceptPattern]:
    """Convert Neo4j rows into recovery patterns."""
    out: list[LocalConceptPattern] = []
    for row in rows or []:
        cid = str(row.get("concept_id") or "").strip()
        if not cid.startswith("LEO-"):
            continue
        out.append(
            LocalConceptPattern(
                normalized=str(row.get("normalized") or ""),
                form=str(row.get("form") or row.get("normalized") or ""),
                concept_id=cid,
                fsn=str(row.get("fsn") or cid),
                semantic_tag=str(row.get("semantic_tag") or "finding"),
            )
        )
    return out


FETCH_ACTIVE_PACKAGE_PATTERNS = """
MATCH (p:LocalTerminologyPackage {status: 'active'})-[:CONTAINS]->(c:Concept)
WHERE coalesce(c.is_local, false) = true
  AND coalesce(c.code_system, '') = $code_system
  AND c.active = true
  AND (
    p.scope = 'global'
    OR ($org_id IS NOT NULL AND p.scope = 'tenant' AND p.org_id = $org_id)
  )
MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c)
WHERE coalesce(sf.status, 'approved') IN ['approved', 'active']
RETURN sf.normalized AS normalized,
       sf.form AS form,
       c.id AS concept_id,
       coalesce(c.fsn, c.preferred_term, c.id) AS fsn,
       coalesce(c.semantic_tag, c.concept_kind, 'finding') AS semantic_tag,
       p.scope AS package_scope,
       p.org_id AS package_org_id,
       p.id AS package_id
"""


def dedupe_tenant_over_global(
    rows: list[dict[str, Any]],
) -> list[LocalConceptPattern]:
    """Prefer tenant package rows over global for the same normalized form."""
    by_norm: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        key = str(row.get("normalized") or "").strip().lower()
        if not key:
            continue
        existing = by_norm.get(key)
        if existing is None:
            by_norm[key] = row
            continue
        if (
            existing.get("package_scope") == "global"
            and row.get("package_scope") == "tenant"
        ):
            by_norm[key] = row
    return patterns_from_rows(list(by_norm.values()))


def load_active_package_patterns(
    client: Any,
    org_id: str | None,
) -> list[LocalConceptPattern]:
    """Load approved local aliases from active global (+ tenant) packages.

    Draft and retired packages never contribute. When org_id is empty, only
    global active packages are returned.
    """
    oid = (org_id or "").strip() or None
    rows = client.run(
        FETCH_ACTIVE_PACKAGE_PATTERNS,
        code_system=CODE_SYSTEM_LEO_LOCAL,
        org_id=oid,
    )
    return dedupe_tenant_over_global(rows or [])
