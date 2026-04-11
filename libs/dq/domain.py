"""Domain ValueSet coverage and pathway gap analysis."""

from __future__ import annotations

import logging
from typing import Any, Optional

from libs.dq._filters import DQFilters
from libs.dq._models import DomainCoverageResult, OrphanConcept, PathwayGap

logger = logging.getLogger(__name__)

_ORPHAN_CONCEPTS_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[d:DOCUMENTS]->(c)
WHERE c.conceptId IS NOT NULL
WITH toString(c.conceptId) AS cid, c.name AS name, count(DISTINCT p) AS pts
OPTIONAL MATCH (kgc {conceptId: cid})
WHERE kgc IS NULL OR coalesce(kgc.active, true) = false
WITH cid, name, pts, kgc
WHERE kgc IS NULL
RETURN cid AS concept_id, name, pts AS patient_count
ORDER BY pts DESC
LIMIT $limit
"""

_PATHWAY_GAPS_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress' OR ep.status STARTS WITH 'stale'
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE]->(ep)
RETURN ep.id AS episode_id,
       p.id AS patient_id,
       ep.cancer_type AS site,
       ep.referral_date AS referral_date,
       ep.referral_date IS NOT NULL AS has_referral,
       ep.specialist_seen AS has_specialist,
       false AS has_diagnosis
LIMIT $limit
"""

_VALUESET_CONCEPTS_Q = """
MATCH (vs:ValueSet {id: $domain_id})-[:INCLUDES]->(c)
RETURN count(*) AS cnt
"""

_ENCOUNTER_CONCEPTS_NOT_IN_VS_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c)
WHERE NOT EXISTS {
    MATCH (vs:ValueSet {id: $domain_id})-[:INCLUDES]->(c)
}
RETURN toString(c.conceptId) AS concept_id,
       c.name AS preferred_term,
       c.semanticTag AS semantic_tag,
       count(*) AS encounter_count
ORDER BY encounter_count DESC
LIMIT $limit
"""


def get_domain_coverage(
    domain_id: str,
    patient_client: Any,
    kg_client: Any,
    limit: int = 500,
) -> DomainCoverageResult:
    """Return concepts outside ValueSets and orphan codes."""
    from libs.neo4j_client.client import run_with_retry

    vs_rows = run_with_retry(kg_client, _VALUESET_CONCEPTS_Q, domain_id=domain_id)
    vs_count = int(vs_rows[0]["cnt"]) if vs_rows else 0

    enc_rows = run_with_retry(
        patient_client,
        _ENCOUNTER_CONCEPTS_NOT_IN_VS_Q,
        domain_id=domain_id,
        limit=limit,
    )

    orphan_rows = run_with_retry(patient_client, _ORPHAN_CONCEPTS_Q, limit=100)
    orphans = [
        OrphanConcept(
            concept_id=r.get("concept_id") or "",
            preferred_term=r.get("name"),
            active=False,
            patient_count=int(r.get("patient_count") or 0),
        )
        for r in orphan_rows
    ]

    return DomainCoverageResult(
        domain_id=domain_id,
        total_concepts_in_valueset=vs_count,
        encounter_concepts_not_in_valueset=len(enc_rows),
        orphan_concepts=orphans,
        pathway_gaps=[],
    )


def get_pathway_gaps(
    patient_client: Any, filters: Optional[DQFilters] = None
) -> list[PathwayGap]:
    """Return pathway gap analysis: referral-no-diagnosis, etc."""
    from libs.neo4j_client.client import run_with_retry

    f = filters or DQFilters()
    rows = run_with_retry(patient_client, _PATHWAY_GAPS_Q, limit=f.limit)
    gaps = []
    for r in rows:
        if r.get("has_referral") and not r.get("has_specialist"):
            gaps.append(
                PathwayGap(
                    patient_id=r.get("patient_id") or "",
                    episode_id=r.get("episode_id"),
                    site=r.get("site") or "unknown",
                    gap_type="referral_no_specialist",
                    date=r.get("referral_date"),
                )
            )
        if not r.get("has_referral"):
            gaps.append(
                PathwayGap(
                    patient_id=r.get("patient_id") or "",
                    episode_id=r.get("episode_id"),
                    site=r.get("site") or "unknown",
                    gap_type="no_referral",
                )
            )
    return gaps


def get_orphan_concepts(patient_client: Any, limit: int = 500) -> list[OrphanConcept]:
    """Return concept IDs on patient data not found or inactive in KG."""
    from libs.neo4j_client.client import run_with_retry

    rows = run_with_retry(patient_client, _ORPHAN_CONCEPTS_Q, limit=limit)
    return [
        OrphanConcept(
            concept_id=r.get("concept_id") or "",
            preferred_term=r.get("name"),
            active=False,
            patient_count=int(r.get("patient_count") or 0),
        )
        for r in rows
    ]
