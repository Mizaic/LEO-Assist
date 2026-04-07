"""Surface form and concept audit service."""
from __future__ import annotations

import logging
from typing import Any, Optional

from libs.dq._models import (
    ConceptStatus,
    MapsToEdge,
    PinVerifyResult,
    ResolveTestResult,
    SurfaceFormAuditResult,
    SurfaceFormDetail,
)

logger = logging.getLogger(__name__)

_SF_AUDIT_Q = """
MATCH (sf:SurfaceForm)
OPTIONAL MATCH (sf)-[m:MAPS_TO]->(c)
WITH sf,
     collect({concept_id: toString(c.conceptId), score: m.score,
              source: m.source, active: c.active,
              preferred_term: c.preferredTerm}) AS edges
RETURN sf.normalizedText AS normalized_term,
       sf.text AS raw_form,
       edges,
       size(edges) AS edge_count
LIMIT $limit
"""

_SF_INSPECT_Q = """
MATCH (sf:SurfaceForm {normalizedText: $term})
OPTIONAL MATCH (sf)-[m:MAPS_TO]->(c)
RETURN sf.normalizedText AS normalized_term,
       sf.text AS raw_form,
       collect({concept_id: toString(c.conceptId),
                preferred_term: c.preferredTerm,
                score: m.score, source: m.source,
                active: coalesce(c.active, true)}) AS edges
"""

_CONCEPT_Q = """
MATCH (c {conceptId: $concept_id})
RETURN toString(c.conceptId) AS concept_id,
       c.preferredTerm AS preferred_term,
       coalesce(c.active, true) AS active,
       c.semanticTag AS semantic_tag,
       c.replacementConceptId AS replacement_id
LIMIT 1
"""


def get_surface_form_audit(
    kg_client: Any, limit: int = 5000
) -> SurfaceFormAuditResult:
    """Return health metrics for all surface forms."""
    from libs.neo4j_client.client import run_with_retry

    rows = run_with_retry(kg_client, _SF_AUDIT_Q, limit=limit)
    orphans, duplicates, inactive, low_conf = 0, 0, 0, 0
    anomalous: list[SurfaceFormDetail] = []

    for r in rows:
        edges = r.get("edges") or []
        edge_count = int(r.get("edge_count") or 0)
        is_orphan = edge_count == 0
        has_inactive = any(e.get("active") is False for e in edges)
        scores = [e.get("score") or 0.0 for e in edges]
        is_low_conf = any(s < 0.5 for s in scores)
        is_dup = edge_count > 1

        if is_orphan:
            orphans += 1
        if is_dup:
            duplicates += 1
        if has_inactive:
            inactive += 1
        if is_low_conf:
            low_conf += 1

        if is_orphan or is_dup or has_inactive or is_low_conf:
            anomalous.append(SurfaceFormDetail(
                normalized_term=r.get("normalized_term") or "",
                raw_form=r.get("raw_form"),
                maps_to=[
                    MapsToEdge(
                        concept_id=e.get("concept_id") or "",
                        preferred_term=e.get("preferred_term"),
                        score=float(e.get("score") or 0.0),
                        source=e.get("source"),
                        active=bool(e.get("active", True)),
                    )
                    for e in edges
                ],
                is_orphan=is_orphan,
                has_inactive_target=has_inactive,
            ))

    return SurfaceFormAuditResult(
        total_count=len(rows),
        orphan_count=orphans,
        duplicate_count=duplicates,
        inactive_target_count=inactive,
        low_confidence_count=low_conf,
        anomalous_forms=anomalous[:200],
    )


def inspect_surface_form(
    normalized_term: str, kg_client: Any
) -> Optional[SurfaceFormDetail]:
    """Return detail for a single surface form by normalized text."""
    from libs.neo4j_client.client import run_with_retry

    rows = run_with_retry(
        kg_client, _SF_INSPECT_Q, term=normalized_term
    )
    if not rows:
        return None
    r = rows[0]
    edges = r.get("edges") or []
    return SurfaceFormDetail(
        normalized_term=r.get("normalized_term") or normalized_term,
        raw_form=r.get("raw_form"),
        maps_to=[
            MapsToEdge(
                concept_id=e.get("concept_id") or "",
                preferred_term=e.get("preferred_term"),
                score=float(e.get("score") or 0.0),
                source=e.get("source"),
                active=bool(e.get("active", True)),
            )
            for e in edges
        ],
        is_orphan=len(edges) == 0,
        has_inactive_target=any(
            e.get("active") is False for e in edges
        ),
    )


def batch_resolve_test(
    terms: list[str], term_client: Any
) -> list[ResolveTestResult]:
    """Batch HTTP resolver smoke test: return pass/fail per term."""
    results = []
    for t in terms:
        try:
            resolved = term_client.resolve_one(t)
            if resolved:
                results.append(ResolveTestResult(
                    term=t,
                    resolved_concept_id=str(resolved.concept_id),
                    resolved_term=resolved.preferred_term,
                    score=resolved.score,
                    status="pass",
                ))
            else:
                results.append(ResolveTestResult(term=t, status="fail"))
        except Exception as exc:
            logger.warning("resolve_test error for %r: %s", t, exc)
            results.append(ResolveTestResult(term=t, status="error"))
    return results


def batch_pin_verify(
    pins: list[dict], kg_client: Any, term_client: Any
) -> list[PinVerifyResult]:
    """Verify phrase->concept pins exist in KG and HTTP resolve."""
    from libs.neo4j_client.client import run_with_retry

    CHECK_Q = """
    MATCH (sf:SurfaceForm {normalizedText: $term})-[:MAPS_TO]->(c {conceptId: $cid})
    RETURN count(*) AS cnt
    """
    results = []
    for pin in pins:
        phrase = pin.get("phrase") or ""
        cid = pin.get("concept_id") or ""
        # KG check
        rows = run_with_retry(kg_client, CHECK_Q, term=phrase, cid=cid)
        kg_ok = bool(rows and int(rows[0].get("cnt") or 0) > 0)
        # HTTP resolve check
        http_ok = False
        try:
            resolved = term_client.resolve_one(phrase)
            if resolved and str(resolved.concept_id) == str(cid):
                http_ok = True
        except Exception:
            pass
        results.append(PinVerifyResult(
            phrase=phrase,
            concept_id=cid,
            kg_edge_exists=kg_ok,
            http_resolves=http_ok,
            status="pass" if (kg_ok and http_ok) else "fail",
        ))
    return results


def get_concept_status(
    concept_ids: list[str], kg_client: Any
) -> list[ConceptStatus]:
    """Return active/inactive status and preferred term for concept IDs."""
    from libs.neo4j_client.client import run_with_retry

    results = []
    for cid in concept_ids:
        rows = run_with_retry(kg_client, _CONCEPT_Q, concept_id=cid)
        if rows:
            r = rows[0]
            results.append(ConceptStatus(
                concept_id=r.get("concept_id") or cid,
                preferred_term=r.get("preferred_term"),
                active=bool(r.get("active", True)),
                semantic_tag=r.get("semantic_tag"),
                replacement_id=r.get("replacement_id"),
            ))
        else:
            results.append(ConceptStatus(
                concept_id=cid, active=False
            ))
    return results
