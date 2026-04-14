"""Domain configuration endpoints.

Two-level hierarchy:
  AuditDomain  (Cancer Audit, Cardiology Audit, QOF, ...)
    -> Subdomain  (cancer_types, referrals, treatment, symptoms, ...)
        -> SNOMED concepts with terms and surface forms

AuditDomain nodes live in the Knowledge Graph.
Subdomains are ValueSet nodes linked via (AuditDomain)-[:HAS_SUBDOMAIN]->(ValueSet).
ValueSet nodes carry flat properties (milestoneType, semanticTags, etc.) for
efficient Cypher queries; rawJson is only kept as an optional audit trail.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.terminology_queries import DESCENDANTS_TEMPLATE
from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(scope: CallerScope = Depends(get_caller_scope)) -> CallerScope:
    """Raise 403 unless the caller is a platform admin."""
    if not scope.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return scope


SNOMED_SYSTEM = "http://snomed.info/sct"

# ── Helpers ───────────────────────────────────────────────────────────────


def _subdomain_to_valueset_id(subdomain_name: str) -> str:
    return f"ncda-{subdomain_name.replace('_', '-')}"


def _valueset_id_to_subdomain(vs_id: str) -> str:
    if vs_id.startswith("ncda-"):
        return vs_id[5:].replace("-", "_")
    return vs_id


def _ensure_default_domain() -> None:
    """Create a default 'cancer_audit' AuditDomain linked to existing ncda-* ValueSets.

    Also removes duplicate HAS_SUBDOMAIN relationships that can accumulate due to
    concurrent MERGE calls (Neo4j has no uniqueness constraint on relationships).
    """
    client = KnowledgeGraphClient()
    try:
        existing = client.run("MATCH (d:AuditDomain) RETURN count(d) AS cnt")
        if existing and existing[0].get("cnt", 0) > 0:
            # Remove any duplicate HAS_SUBDOMAIN rels regardless of how domain was seeded.
            client.run(
                "MATCH (d:AuditDomain)-[r:HAS_SUBDOMAIN]->(v:ValueSet) "
                "WITH d, v, collect(r) AS rels "
                "WHERE size(rels) > 1 "
                "FOREACH (dup IN tail(rels) | DELETE dup)"
            )
            return

        vs_rows = client.run(
            "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' RETURN v.id AS id"
        )
        if not vs_rows:
            return

        domain_id = "cancer_audit"
        client.run(
            "MERGE (d:AuditDomain {id: $id}) "
            "SET d.name = $name, d.description = $desc, d.source = 'platform'",
            id=domain_id,
            name="Cancer Audit",
            desc="National Cancer Diagnosis Audit domains",
        )
        for r in vs_rows:
            vs_id = r.get("id")
            if vs_id:
                client.run(
                    "MATCH (d:AuditDomain {id: $did}), (v:ValueSet {id: $vid}) "
                    "MERGE (d)-[:HAS_SUBDOMAIN]->(v)",
                    did=domain_id,
                    vid=vs_id,
                )
        logger.info(
            "Created default cancer_audit domain with %d subdomains", len(vs_rows)
        )
    finally:
        client.close()


def _count_concepts_from_raw(raw_json: Optional[str]) -> int:
    """Count SNOMED concepts stored in the rawJson compose.include blob."""
    if not raw_json:
        return 0
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return 0
    total = 0
    for include in (vs.get("compose") or {}).get("include") or []:
        total += len(include.get("concept") or [])
    return total


def _parse_concepts_from_raw(raw_json: Optional[str]) -> List[Dict[str, Any]]:
    """Extract concept list from rawJson for detail views."""
    if not raw_json:
        return []
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []
    concepts: List[Dict[str, Any]] = []
    for include in (vs.get("compose") or {}).get("include") or []:
        for c in include.get("concept") or []:
            code = c.get("code", "")
            display = c.get("display", "")
            try:
                concept_id = int(code)
            except (ValueError, TypeError):
                concept_id = 0
            designations = c.get("designation") or []
            synonyms = [
                d.get("value", "")
                for d in designations
                if (d.get("use") or {}).get("code") == "synonym"
            ]
            benchmark_key = next(
                (
                    d.get("value")
                    for d in designations
                    if (d.get("use") or {}).get("code") == "benchmark_key"
                ),
                None,
            )
            concepts.append(
                {
                    "concept_id": concept_id,
                    "term": display,
                    "preferred_term": display,
                    "semantic_tag": None,
                    "guideline_synonyms": synonyms,
                    "benchmark_key": benchmark_key,
                }
            )
    return concepts


def _get_valueset_raw(vs_id: str) -> Optional[str]:
    """Fetch the rawJson string for a ValueSet node."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:ValueSet {id: $vsid}) RETURN v.rawJson AS rj",
            vsid=vs_id,
        )
        if not rows:
            return None
        return rows[0].get("rj")
    finally:
        client.close()


_VALUESET_READ_QUERY = (
    "MATCH (v:ValueSet {id: $id}) "
    "RETURN v.name AS name, v.description AS description, "
    "       v.milestoneType AS milestoneType, "
    "       v.timeWindowMonths AS timeWindowMonths, "
    "       v.semanticTags AS semanticTags, "
    "       coalesce(v.assertionFilter, []) AS assertionFilter, "
    "       coalesce(v.constructs, []) AS constructs, "
    "       v.rawJson AS rawJson"
)


def _parse_list_prop(val) -> List[str]:
    """Coerce a Neo4j property (list or JSON string) to a Python list of strings."""
    if not val:
        return []
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return list(val) if isinstance(val, (list, tuple)) else []


def _parse_constructs_prop(val: Any) -> List[Dict[str, Any]]:
    """Coerce a Neo4j property (list or JSON string) to construct rows."""
    if not val:
        return []
    parsed = val
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def _batch_child_counts(concept_ids: List[str], depth: int = 3) -> Dict[str, int]:
    """Single round-trip IS_A descendant count for a list of SNOMED concept IDs."""
    if not concept_ids:
        return {}
    cypher = (
        f"MATCH (ancestor:Concept)<-[:IS_A*1..{depth}]-(d:Concept) "
        "WHERE ancestor.id IN $ids AND d.active = true "
        "RETURN ancestor.id AS concept_id, count(DISTINCT d) AS child_count"
    )
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(cypher, ids=concept_ids)
        return {r["concept_id"]: r["child_count"] for r in (rows or [])}
    finally:
        kg.close()


def _enrich_with_child_counts(concepts: List[Dict[str, Any]]) -> None:
    """Add child_count in-place via a single batch IS_A query.

    Concepts with no IS_A children get child_count=0 (leaf/specific concept).
    """
    if not concepts:
        return
    ids = [str(c["concept_id"]) for c in concepts if c.get("concept_id")]
    counts = _batch_child_counts(ids)
    for c in concepts:
        c["child_count"] = counts.get(str(c["concept_id"]), 0)


def _valueset_row_to_subdomain_detail(
    vr: Dict[str, Any], subdomain_name: str
) -> SubdomainDetail:
    concepts = _parse_concepts_from_raw(vr.get("rawJson"))
    _enrich_with_child_counts(concepts)
    constructs = _parse_constructs_prop(vr.get("constructs"))
    return SubdomainDetail(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=_parse_list_prop(vr.get("semanticTags")),
        assertion_filter=_parse_list_prop(vr.get("assertionFilter")),
        constructs=constructs,
        construct_count=len(constructs),
        concepts=concepts,
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


def _upsert_valueset_flat(vs_id: str, vs_dict: Dict[str, Any]) -> None:
    """Write a ValueSet to the KG with flat properties + rawJson backup."""
    name = vs_dict.get("name", "")
    description = vs_dict.get("description", "")
    title = vs_dict.get("title", description)
    status = vs_dict.get("status", "active")

    milestone_type = vs_dict.get("milestoneType")
    time_window_months = vs_dict.get("timeWindowMonths")
    semantic_tags = vs_dict.get("semanticTags", [])
    assertion_filter = vs_dict.get("assertionFilter", [])
    constructs = vs_dict.get("constructs", [])

    if milestone_type is None or time_window_months is None or not semantic_tags:
        for ext in vs_dict.get("extension") or []:
            if ext.get("url", "").endswith("/domain-config"):
                for sub in ext.get("extension") or []:
                    u = sub.get("url", "")
                    if u == "milestoneType" and milestone_type is None:
                        milestone_type = sub.get("valueCode")
                    elif u == "timeWindowMonths" and time_window_months is None:
                        time_window_months = sub.get("valueInteger")
                    elif u == "semanticTag" and not semantic_tags:
                        t = sub.get("valueString")
                        if t:
                            semantic_tags.append(t)

    raw_json = json.dumps(vs_dict)

    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (v:ValueSet {id: $id}) "
            "SET v.name = $name, "
            "    v.title = $title, "
            "    v.description = $description, "
            "    v.status = $status, "
            "    v.resourceType = 'ValueSet', "
            "    v.milestoneType = $mt, "
            "    v.timeWindowMonths = $twm, "
            "    v.semanticTags = $tags, "
            "    v.assertionFilter = $af, "
            "    v.constructs = $constructs, "
            "    v.rawJson = $raw",
            id=vs_id,
            name=name,
            title=title,
            description=description,
            status=status,
            mt=milestone_type,
            twm=time_window_months,
            tags=semantic_tags,
            af=assertion_filter,
            constructs=constructs,
            raw=raw_json,
        )
    finally:
        client.close()


# ── Response models ──────────────────────────────────────────────────────


class SubdomainSummary(BaseModel):
    name: str
    description: str
    milestone_type: Optional[str] = None
    time_window_months: Optional[int] = None
    semantic_tags: List[str] = []
    assertion_filter: List[str] = []
    constructs: List[Dict[str, Any]] = []
    construct_count: int = 0
    concept_count: int = 0
    descendant_count: int = 0


class SubdomainDetail(SubdomainSummary):
    concepts: List[Dict[str, Any]] = []


class DomainSummary(BaseModel):
    id: str
    name: str
    description: str
    subdomain_count: int = 0
    source: str = "tenant"
    episode_detector: bool = False


class DomainDetail(DomainSummary):
    subdomains: List[SubdomainSummary] = []


class DomainCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    episode_detector: bool = False


class DomainUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    episode_detector: Optional[bool] = None


class SubdomainCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    milestone_type: Optional[str] = None
    time_window_months: Optional[int] = None
    semantic_tags: List[str] = []
    assertion_filter: List[str] = []
    constructs: List[Dict[str, Any]] = []


class SubdomainUpdateRequest(BaseModel):
    description: Optional[str] = None
    milestone_type: Optional[str] = None
    time_window_months: Optional[int] = None
    semantic_tags: Optional[List[str]] = None
    assertion_filter: Optional[List[str]] = None
    constructs: Optional[List[Dict[str, Any]]] = None


class AddConceptRequest(BaseModel):
    concept_id: int
    term: str = Field(..., min_length=1)
    synonyms: List[str] = []
    benchmark_key: Optional[str] = None


class ConstructRoleRequest(BaseModel):
    role: str = Field(..., min_length=1)
    concept_ids: List[int] = []
    required: bool = True


class ConstructDefinitionRequest(BaseModel):
    id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    description: str = ""
    logic: str = "ALL"
    roles: List[ConstructRoleRequest] = []


# ── Domain endpoints ─────────────────────────────────────────────────────


@router.get("/domains", response_model=List[DomainSummary])
def list_domains(
    scope: CallerScope = Depends(get_caller_scope),
    source: Optional[str] = Query(
        default=None, description="Filter by source: nice, platform, or tenant"
    ),
):
    """List all audit domains.

    Use the ``source`` query parameter to filter:
    - ``nice`` — areas from official NICE guidelines
    - ``platform`` — built-in domains provided out of the box
    - ``tenant`` — domains created by your organisation
    """
    _ensure_default_domain()
    client = KnowledgeGraphClient()
    try:
        if source:
            cypher = (
                "MATCH (d:AuditDomain) "
                "WHERE coalesce(d.source, 'tenant') = $source "
                "OPTIONAL MATCH (d)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
                "RETURN d.id AS id, d.name AS name, d.description AS description, "
                "coalesce(d.source, 'tenant') AS source, "
                "coalesce(d.episodeDetector, false) AS episode_detector, "
                "count(DISTINCT v) AS subdomain_count "
                "ORDER BY d.name"
            )
            rows = client.run(cypher, source=source)
        else:
            rows = client.run(
                "MATCH (d:AuditDomain) "
                "OPTIONAL MATCH (d)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
                "RETURN d.id AS id, d.name AS name, d.description AS description, "
                "coalesce(d.source, 'tenant') AS source, "
                "coalesce(d.episodeDetector, false) AS episode_detector, "
                "count(DISTINCT v) AS subdomain_count "
                "ORDER BY d.name"
            )
        return [
            DomainSummary(
                id=r["id"],
                name=r["name"] or r["id"],
                description=r.get("description") or "",
                subdomain_count=r.get("subdomain_count", 0),
                source=r.get("source", "tenant"),
                episode_detector=bool(r.get("episode_detector", False)),
            )
            for r in rows
        ]
    finally:
        client.close()


class SubdomainMembershipItem(BaseModel):
    domain_id: str
    domain_name: str
    subdomain_name: str
    subdomain_label: str
    is_member: bool


class ConceptMembershipsResponse(BaseModel):
    concept_id: str
    subdomains: List[SubdomainMembershipItem]


@router.get("/concepts/{concept_id}/subdomain-memberships")
def get_concept_subdomain_memberships(
    concept_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> ConceptMembershipsResponse:
    """Single-query endpoint: returns all subdomains with an is_member flag.

    Replaces the previous N+M per-subdomain fetch pattern used by the
    SNOMED lookup dialog in the operations UI.
    """
    _ensure_default_domain()
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "WITH DISTINCT d, v "
            "RETURN d.id AS domain_id, coalesce(d.name, d.id) AS domain_name, "
            "       coalesce(v.name, v.id) AS subdomain_name, "
            "       v.rawJson AS raw_json "
            "ORDER BY d.name, v.name"
        )
    finally:
        client.close()

    items: List[SubdomainMembershipItem] = []
    seen: set = set()
    for row in rows or []:
        d_id = row["domain_id"]
        sub_name = row["subdomain_name"]
        key = f"{d_id}::{sub_name}"
        if key in seen:
            continue
        seen.add(key)
        concepts = _parse_concepts_from_raw(row.get("raw_json"))
        is_member = any(str(c.get("concept_id")) == str(concept_id) for c in concepts)
        items.append(
            SubdomainMembershipItem(
                domain_id=d_id,
                domain_name=row["domain_name"],
                subdomain_name=sub_name,
                subdomain_label=sub_name.replace("_", " "),
                is_member=is_member,
            )
        )
    return ConceptMembershipsResponse(concept_id=concept_id, subdomains=items)


@router.post("/domains", response_model=DomainSummary, status_code=201)
def create_domain(
    body: DomainCreateRequest, scope: CallerScope = Depends(_require_admin)
):
    """Create a new audit domain."""
    domain_id = body.name.lower().replace(" ", "_").replace("-", "_")
    client = KnowledgeGraphClient()
    try:
        existing = client.run(
            "MATCH (d:AuditDomain {id: $id}) RETURN d.id AS id", id=domain_id
        )
        if existing:
            raise HTTPException(400, f"Domain '{body.name}' already exists")
        client.run(
            "CREATE (d:AuditDomain {id: $id, name: $name, description: $desc, "
            "source: 'tenant', episodeDetector: $ep_det, createdAt: datetime()})",
            id=domain_id,
            name=body.name,
            desc=body.description,
            ep_det=body.episode_detector,
        )
        return DomainSummary(
            id=domain_id,
            name=body.name,
            description=body.description,
            subdomain_count=0,
            source="tenant",
            episode_detector=body.episode_detector,
        )
    finally:
        client.close()


@router.get("/domains/{domain_id}", response_model=DomainDetail)
def get_domain(domain_id: str, scope: CallerScope = Depends(get_caller_scope)):
    """Get domain with its subdomains (reads flat properties, no JSON parsing)."""
    _ensure_default_domain()
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain {id: $id}) "
            "RETURN d.id AS id, d.name AS name, d.description AS description, "
            "coalesce(d.source, 'tenant') AS source, "
            "coalesce(d.episodeDetector, false) AS episode_detector",
            id=domain_id,
        )
        if not rows:
            raise HTTPException(404, f"Domain '{domain_id}' not found")

        d = rows[0]

        vs_rows = client.run(
            "MATCH (d:AuditDomain {id: $id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "WITH DISTINCT v "
            "RETURN v.id AS vid, v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       coalesce(v.assertionFilter, []) AS assertionFilter, "
            "       coalesce(v.constructs, []) AS constructs, "
            "       v.rawJson AS rawJson "
            "ORDER BY v.name",
            id=domain_id,
        )

        # Parse concepts per subdomain so we can batch-query IS_A counts.
        parsed: List[tuple] = []
        for vr in vs_rows:
            subdomain_name = vr.get("name") or _valueset_id_to_subdomain(vr["vid"])
            concepts = _parse_concepts_from_raw(vr.get("rawJson"))
            concept_ids = [
                str(c["concept_id"]) for c in concepts if c.get("concept_id")
            ]
            parsed.append((vr, subdomain_name, concept_ids))

        all_ids = [cid for _, _, ids in parsed for cid in ids]
        child_counts = _batch_child_counts(all_ids)

        subdomains: List[SubdomainSummary] = []
        for vr, subdomain_name, concept_ids in parsed:
            desc_count = sum(child_counts.get(cid, 0) for cid in concept_ids)
            constructs = _parse_constructs_prop(vr.get("constructs"))
            subdomains.append(
                SubdomainSummary(
                    name=subdomain_name,
                    description=vr.get("description") or "",
                    milestone_type=vr.get("milestoneType"),
                    time_window_months=vr.get("timeWindowMonths"),
                    semantic_tags=_parse_list_prop(vr.get("semanticTags")),
                    assertion_filter=_parse_list_prop(vr.get("assertionFilter")),
                    constructs=constructs,
                    construct_count=len(constructs),
                    concept_count=len(concept_ids),
                    descendant_count=desc_count,
                )
            )

        return DomainDetail(
            id=d["id"],
            name=d["name"] or d["id"],
            description=d.get("description") or "",
            subdomain_count=len(subdomains),
            subdomains=subdomains,
            source=d.get("source", "tenant"),
            episode_detector=bool(d.get("episode_detector", False)),
        )
    finally:
        client.close()


@router.put("/domains/{domain_id}", response_model=DomainSummary)
def update_domain(
    domain_id: str,
    body: DomainUpdateRequest,
    scope: CallerScope = Depends(_require_admin),
):
    """Update domain metadata."""
    client = KnowledgeGraphClient()
    try:
        existing = client.run(
            "MATCH (d:AuditDomain {id: $id}) RETURN d.id AS id", id=domain_id
        )
        if not existing:
            raise HTTPException(404, f"Domain '{domain_id}' not found")

        sets = []
        params: Dict[str, Any] = {"id": domain_id}
        if body.name is not None:
            sets.append("d.name = $name")
            params["name"] = body.name
        if body.description is not None:
            sets.append("d.description = $desc")
            params["desc"] = body.description
        if body.episode_detector is not None:
            sets.append("d.episodeDetector = $ep_det")
            params["ep_det"] = body.episode_detector

        if sets:
            client.run(
                f"MATCH (d:AuditDomain {{id: $id}}) SET {', '.join(sets)}", **params
            )

        rows = client.run(
            "MATCH (d:AuditDomain {id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "RETURN d.id AS id, d.name AS name, d.description AS description, "
            "coalesce(d.episodeDetector, false) AS episode_detector, "
            "count(v) AS subdomain_count",
            id=domain_id,
        )
        r = rows[0]
        return DomainSummary(
            id=r["id"],
            name=r["name"] or r["id"],
            description=r.get("description") or "",
            subdomain_count=r.get("subdomain_count", 0),
            episode_detector=bool(r.get("episode_detector", False)),
        )
    finally:
        client.close()


@router.delete("/domains/{domain_id}", status_code=204)
def delete_domain(domain_id: str, scope: CallerScope = Depends(_require_admin)):
    """Delete an audit domain (does not delete subdomains/ValueSets).

    NICE domains (source=nice) and platform domains (source=platform)
    cannot be deleted. These are protected system domains.
    """
    client = KnowledgeGraphClient()
    try:
        existing = client.run(
            "MATCH (d:AuditDomain {id: $id}) RETURN d.id AS id, coalesce(d.source, 'tenant') AS source",
            id=domain_id,
        )
        if not existing:
            raise HTTPException(404, f"Domain '{domain_id}' not found")
        domain_source = existing[0].get("source", "tenant")
        if domain_source in ("nice", "platform"):
            raise HTTPException(
                403,
                f"This domain cannot be deleted because it is a "
                f"{'NICE guideline' if domain_source == 'nice' else 'built-in platform'} domain. "
                "You can manage its concepts, but you cannot delete it.",
            )
        client.run("MATCH (d:AuditDomain {id: $id}) DETACH DELETE d", id=domain_id)
    finally:
        client.close()


@router.delete("/domains/{domain_id}/subdomains/{subdomain_name}", status_code=204)
def delete_subdomain(
    domain_id: str,
    subdomain_name: str,
    scope: CallerScope = Depends(_require_admin),
):
    """Delete a subdomain (ValueSet) and remove its link from the domain.

    The ValueSet node is detached and deleted. This cannot be undone.
    """
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)
    vs_id = _subdomain_to_valueset_id(subdomain_name)
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (v:ValueSet {id: $id}) DETACH DELETE v",
            id=vs_id,
        )
    finally:
        client.close()
    DomainRegistry.reset_instance()


# ── Subdomain endpoints ──────────────────────────────────────────────────


@router.post(
    "/domains/{domain_id}/subdomains",
    response_model=SubdomainSummary,
    status_code=201,
)
def create_subdomain(
    domain_id: str,
    body: SubdomainCreateRequest,
    scope: CallerScope = Depends(_require_admin),
):
    """Create a new subdomain (ValueSet) and link it to the domain."""
    client = KnowledgeGraphClient()
    try:
        existing = client.run(
            "MATCH (d:AuditDomain {id: $id}) RETURN d.id AS id", id=domain_id
        )
        if not existing:
            raise HTTPException(404, f"Domain '{domain_id}' not found")
    finally:
        client.close()

    subdomain_name = body.name.lower().replace(" ", "_").replace("-", "_")
    vs_id = _subdomain_to_valueset_id(subdomain_name)

    check = KnowledgeGraphClient()
    try:
        dup = check.run("MATCH (v:ValueSet {id: $id}) RETURN v.id AS id", id=vs_id)
        if dup:
            raise HTTPException(400, f"Subdomain '{body.name}' already exists")
    finally:
        check.close()

    resource = {
        "resourceType": "ValueSet",
        "id": vs_id,
        "status": "active",
        "name": subdomain_name,
        "title": body.description or body.name,
        "description": body.description,
        "milestoneType": body.milestone_type,
        "timeWindowMonths": body.time_window_months,
        "semanticTags": body.semantic_tags,
        "assertionFilter": body.assertion_filter,
        "constructs": body.constructs,
        "compose": {"include": [{"system": SNOMED_SYSTEM, "concept": []}]},
    }
    _upsert_valueset_flat(vs_id, resource)

    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (d:AuditDomain {id: $did}), (v:ValueSet {id: $vid}) "
            "MERGE (d)-[:HAS_SUBDOMAIN]->(v)",
            did=domain_id,
            vid=vs_id,
        )
    finally:
        client.close()

    DomainRegistry.reset_instance()

    return SubdomainSummary(
        name=subdomain_name,
        description=body.description,
        milestone_type=body.milestone_type,
        time_window_months=body.time_window_months,
        semantic_tags=body.semantic_tags,
        assertion_filter=body.assertion_filter,
        constructs=body.constructs,
        construct_count=len(body.constructs),
        concept_count=0,
    )


@router.get(
    "/domains/{domain_id}/subdomains/{subdomain_name}",
    response_model=SubdomainDetail,
)
def get_subdomain(
    domain_id: str, subdomain_name: str, scope: CallerScope = Depends(get_caller_scope)
):
    """Get subdomain detail including SNOMED concepts."""
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:ValueSet {id: $id}) "
            "RETURN v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       coalesce(v.assertionFilter, []) AS assertionFilter, "
            "       coalesce(v.constructs, []) AS constructs, "
            "       v.rawJson AS rawJson",
            id=vs_id,
        )
        if not rows:
            raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")
    finally:
        client.close()

    return _valueset_row_to_subdomain_detail(rows[0], subdomain_name)


@router.put(
    "/domains/{domain_id}/subdomains/{subdomain_name}",
    response_model=SubdomainSummary,
)
def update_subdomain(
    domain_id: str,
    subdomain_name: str,
    body: SubdomainUpdateRequest,
    scope: CallerScope = Depends(_require_admin),
):
    """Update subdomain config (flat properties + rawJson sync)."""
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)

    sets = []
    params: Dict[str, Any] = {"id": vs_id}

    if body.description is not None:
        sets.append("v.description = $description")
        params["description"] = body.description
    if body.milestone_type is not None:
        sets.append("v.milestoneType = $mt")
        params["mt"] = body.milestone_type
    if body.time_window_months is not None:
        sets.append("v.timeWindowMonths = $twm")
        params["twm"] = body.time_window_months
    if body.semantic_tags is not None:
        sets.append("v.semanticTags = $tags")
        params["tags"] = body.semantic_tags
    if body.assertion_filter is not None:
        sets.append("v.assertionFilter = $af")
        params["af"] = body.assertion_filter
    if body.constructs is not None:
        sets.append("v.constructs = $constructs")
        params["constructs"] = body.constructs

    client = KnowledgeGraphClient()
    try:
        if sets:
            client.run(
                f"MATCH (v:ValueSet {{id: $id}}) SET {', '.join(sets)}", **params
            )

        rows = client.run(
            "MATCH (v:ValueSet {id: $id}) "
            "RETURN v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       coalesce(v.assertionFilter, []) AS assertionFilter, "
            "       coalesce(v.constructs, []) AS constructs, "
            "       v.rawJson AS rawJson",
            id=vs_id,
        )
        if not rows:
            raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")
    finally:
        client.close()

    vr = rows[0]
    tags = vr.get("semanticTags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    af = vr.get("assertionFilter") or []
    if isinstance(af, str):
        try:
            af = json.loads(af)
        except (json.JSONDecodeError, TypeError):
            af = []

    DomainRegistry.reset_instance()

    return SubdomainSummary(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=tags,
        assertion_filter=af,
        constructs=_parse_constructs_prop(vr.get("constructs")),
        construct_count=len(_parse_constructs_prop(vr.get("constructs"))),
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


def _normalise_construct_rows(
    constructs: List[ConstructDefinitionRequest],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for construct in constructs:
        roles: List[Dict[str, Any]] = []
        for role in construct.roles:
            role_name = role.role.strip()
            concept_ids = [int(cid) for cid in role.concept_ids if int(cid) > 0]
            if not role_name or not concept_ids:
                continue
            roles.append(
                {
                    "role": role_name,
                    "concept_ids": concept_ids,
                    "required": bool(role.required),
                }
            )
        if not roles:
            continue
        rows.append(
            {
                "id": construct.id.strip(),
                "display_name": construct.display_name.strip(),
                "description": construct.description.strip(),
                "logic": construct.logic.strip().upper() or "ALL",
                "roles": roles,
            }
        )
    return rows


# ── Concept endpoints (within a subdomain) ───────────────────────────────


@router.get(
    "/domains/{domain_id}/subdomains/{subdomain_name}/constructs",
    response_model=List[Dict[str, Any]],
)
def list_constructs(
    domain_id: str,
    subdomain_name: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)
    vs_id = _subdomain_to_valueset_id(subdomain_name)
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:ValueSet {id: $id}) "
            "RETURN coalesce(v.constructs, []) AS constructs",
            id=vs_id,
        )
        if not rows:
            raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")
        return _parse_constructs_prop(rows[0].get("constructs"))
    finally:
        client.close()


@router.put(
    "/domains/{domain_id}/subdomains/{subdomain_name}/constructs",
    response_model=SubdomainSummary,
)
def replace_constructs(
    domain_id: str,
    subdomain_name: str,
    body: List[ConstructDefinitionRequest],
    scope: CallerScope = Depends(_require_admin),
):
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)
    vs_id = _subdomain_to_valueset_id(subdomain_name)
    raw = _get_valueset_raw(vs_id)
    if raw is None:
        raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")
    try:
        vs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        vs = {}
    vs["constructs"] = _normalise_construct_rows(body)
    _upsert_valueset_flat(vs_id, vs)
    DomainRegistry.reset_instance()
    client = KnowledgeGraphClient()
    try:
        rows = client.run(_VALUESET_READ_QUERY, id=vs_id)
        if not rows:
            raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")
    finally:
        client.close()
    vr = rows[0]
    constructs = _parse_constructs_prop(vr.get("constructs"))
    return SubdomainSummary(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=_parse_list_prop(vr.get("semanticTags")),
        assertion_filter=_parse_list_prop(vr.get("assertionFilter")),
        constructs=constructs,
        construct_count=len(constructs),
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


@router.post(
    "/domains/{domain_id}/subdomains/{subdomain_name}/concepts",
    response_model=SubdomainDetail,
)
def add_concept(
    domain_id: str,
    subdomain_name: str,
    body: AddConceptRequest,
    scope: CallerScope = Depends(_require_admin),
):
    """Add a SNOMED concept to a subdomain."""
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)
    raw = _get_valueset_raw(vs_id)
    if raw is None:
        raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")

    try:
        vs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        vs = {}

    compose = vs.setdefault("compose", {})
    includes = compose.setdefault("include", [])
    snomed_include = next(
        (i for i in includes if i.get("system") == SNOMED_SYSTEM), None
    )
    if not snomed_include:
        snomed_include = {"system": SNOMED_SYSTEM, "concept": []}
        includes.append(snomed_include)
    concepts = snomed_include.setdefault("concept", [])

    if any(str(c.get("code")) == str(body.concept_id) for c in concepts):
        raise HTTPException(400, f"Concept {body.concept_id} already in subdomain")

    designations = []
    for syn in body.synonyms:
        if syn.strip():
            designations.append({"use": {"code": "synonym"}, "value": syn.strip()})
    if body.benchmark_key and body.benchmark_key.strip():
        designations.append(
            {"use": {"code": "benchmark_key"}, "value": body.benchmark_key.strip()}
        )

    concepts.append(
        {
            "code": str(body.concept_id),
            "display": body.term,
            "designation": designations,
        }
    )

    _upsert_valueset_flat(vs_id, vs)
    DomainRegistry.reset_instance()

    client = KnowledgeGraphClient()
    try:
        rows = client.run(_VALUESET_READ_QUERY, id=vs_id)
    finally:
        client.close()

    return _valueset_row_to_subdomain_detail(rows[0], subdomain_name)


class BatchConceptItem(BaseModel):
    concept_id: int
    term: str = Field(..., min_length=1)


@router.post(
    "/domains/{domain_id}/subdomains/{subdomain_name}/concepts/batch",
    response_model=SubdomainDetail,
)
def add_concepts_batch(
    domain_id: str,
    subdomain_name: str,
    body: List[BatchConceptItem],
    scope: CallerScope = Depends(_require_admin),
):
    """Bulk-add SNOMED concepts to a subdomain, skipping duplicates. Capped at 500 items."""
    if len(body) > 500:
        raise HTTPException(400, "Batch size exceeds maximum of 500 concepts")

    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)
    raw = _get_valueset_raw(vs_id)
    if raw is None:
        raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")

    try:
        vs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        vs = {}

    compose = vs.setdefault("compose", {})
    includes = compose.setdefault("include", [])
    snomed_include = next(
        (i for i in includes if i.get("system") == SNOMED_SYSTEM), None
    )
    if not snomed_include:
        snomed_include = {"system": SNOMED_SYSTEM, "concept": []}
        includes.append(snomed_include)
    concepts = snomed_include.setdefault("concept", [])

    existing_codes = {str(c.get("code")) for c in concepts}
    added = 0
    for item in body:
        code = str(item.concept_id)
        if code not in existing_codes:
            concepts.append({"code": code, "display": item.term, "designation": []})
            existing_codes.add(code)
            added += 1

    _upsert_valueset_flat(vs_id, vs)
    DomainRegistry.reset_instance()

    client = KnowledgeGraphClient()
    try:
        rows = client.run(_VALUESET_READ_QUERY, id=vs_id)
    finally:
        client.close()

    return _valueset_row_to_subdomain_detail(rows[0], subdomain_name)


@router.delete(
    "/domains/{domain_id}/subdomains/{subdomain_name}/concepts/{concept_id}",
    response_model=SubdomainDetail,
)
def remove_concept(
    domain_id: str,
    subdomain_name: str,
    concept_id: str,
    scope: CallerScope = Depends(_require_admin),
):
    """Remove a SNOMED concept from a subdomain."""
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)
    raw = _get_valueset_raw(vs_id)
    if raw is None:
        raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")

    try:
        vs = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        vs = {}

    for include in (vs.get("compose") or {}).get("include") or []:
        if include.get("system") == SNOMED_SYSTEM:
            old = include.get("concept") or []
            include["concept"] = [
                c for c in old if str(c.get("code")) != str(concept_id)
            ]
            break

    _upsert_valueset_flat(vs_id, vs)
    DomainRegistry.reset_instance()

    client = KnowledgeGraphClient()
    try:
        rows = client.run(_VALUESET_READ_QUERY, id=vs_id)
    finally:
        client.close()

    return _valueset_row_to_subdomain_detail(rows[0], subdomain_name)


# ── Export endpoint ──────────────────────────────────────────────────────


@router.get(
    "/domains/{domain_id}/subdomains/{subdomain_name}/export",
)
def export_subdomain(
    domain_id: str,
    subdomain_name: str,
    scope: CallerScope = Depends(get_caller_scope),
    include_children: bool = Query(
        default=False,
        description="When true, expand each concept via IS_A hierarchy and include all descendants",
    ),
    depth: int = Query(
        default=3, ge=1, le=5, description="IS_A traversal depth for child expansion"
    ),
):
    """Export subdomain concept config as JSON.

    Without include_children: returns the stored top-level concepts only.
    With include_children: expands each concept's IS_A descendants and groups them under
    their parent, providing the full set of codes that will match in queries.
    """
    _ensure_domain_owns_subdomain(domain_id, subdomain_name)

    vs_id = _subdomain_to_valueset_id(subdomain_name)
    raw = _get_valueset_raw(vs_id)
    if raw is None:
        raise HTTPException(404, f"Subdomain '{subdomain_name}' not found")

    concepts = _parse_concepts_from_raw(raw)

    if not include_children:
        payload = {
            "domain_id": domain_id,
            "subdomain": subdomain_name,
            "include_children": False,
            "concepts": [
                {
                    "concept_id": c["concept_id"],
                    "term": c["preferred_term"],
                    "synonyms": c.get("guideline_synonyms", []),
                }
                for c in concepts
            ],
        }
        return JSONResponse(
            content=payload,
            headers={
                "Content-Disposition": f'attachment; filename="{subdomain_name}.json"'
            },
        )

    # Expand each concept's IS_A descendants
    kg = KnowledgeGraphClient()
    try:
        expanded = []
        for c in concepts:
            rows = kg.run(
                DESCENDANTS_TEMPLATE.format(depth=int(depth)),
                concept_id=str(c["concept_id"]),
                semantic_tag=None,
                limit=500,
            )
            children = [
                {"concept_id": int(r["snomed_concept_id"]), "term": r["term"]}
                for r in (rows or [])
            ]
            expanded.append(
                {
                    "concept_id": c["concept_id"],
                    "term": c["preferred_term"],
                    "synonyms": c.get("guideline_synonyms", []),
                    "child_count": len(children),
                    "children": children,
                }
            )
    finally:
        kg.close()

    payload = {
        "domain_id": domain_id,
        "subdomain": subdomain_name,
        "include_children": True,
        "expansion_depth": depth,
        "concepts": expanded,
    }
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{subdomain_name}-expanded.json"'
        },
    )


# ── Internal guards ──────────────────────────────────────────────────────


def _ensure_domain_owns_subdomain(domain_id: str, subdomain_name: str) -> None:
    """Verify the domain exists and owns this subdomain."""
    _ensure_default_domain()
    vs_id = _subdomain_to_valueset_id(subdomain_name)
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain {id: $did})-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vid}) "
            "RETURN d.id AS id",
            did=domain_id,
            vid=vs_id,
        )
        if not rows:
            raise HTTPException(
                404,
                f"Subdomain '{subdomain_name}' not found in domain '{domain_id}'",
            )
    finally:
        client.close()
