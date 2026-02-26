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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient

logger = logging.getLogger(__name__)
router = APIRouter()

SNOMED_SYSTEM = "http://snomed.info/sct"

# ── Helpers ───────────────────────────────────────────────────────────────


def _subdomain_to_valueset_id(subdomain_name: str) -> str:
    return f"ncda-{subdomain_name.replace('_', '-')}"


def _valueset_id_to_subdomain(vs_id: str) -> str:
    if vs_id.startswith("ncda-"):
        return vs_id[5:].replace("-", "_")
    return vs_id


def _ensure_default_domain() -> None:
    """Create a default 'cancer_audit' AuditDomain linked to existing ncda-* ValueSets."""
    client = KnowledgeGraphClient()
    try:
        existing = client.run("MATCH (d:AuditDomain) RETURN count(d) AS cnt")
        if existing and existing[0].get("cnt", 0) > 0:
            return

        vs_rows = client.run(
            "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' RETURN v.id AS id"
        )
        if not vs_rows:
            return

        domain_id = "cancer_audit"
        client.run(
            "MERGE (d:AuditDomain {id: $id}) "
            "SET d.name = $name, d.description = $desc",
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
            synonyms = [
                d.get("value", "")
                for d in c.get("designation") or []
                if (d.get("use") or {}).get("code") == "synonym"
            ]
            concepts.append({
                "concept_id": concept_id,
                "term": display,
                "preferred_term": display,
                "semantic_tag": None,
                "guideline_synonyms": synonyms,
            })
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


def _upsert_valueset_flat(vs_id: str, vs_dict: Dict[str, Any]) -> None:
    """Write a ValueSet to the KG with flat properties + rawJson backup."""
    name = vs_dict.get("name", "")
    description = vs_dict.get("description", "")
    title = vs_dict.get("title", description)
    status = vs_dict.get("status", "active")

    milestone_type = vs_dict.get("milestoneType")
    time_window_months = vs_dict.get("timeWindowMonths")
    semantic_tags = vs_dict.get("semanticTags", [])

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
            "    v.rawJson = $raw",
            id=vs_id,
            name=name,
            title=title,
            description=description,
            status=status,
            mt=milestone_type,
            twm=time_window_months,
            tags=semantic_tags,
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
    concept_count: int = 0


class SubdomainDetail(SubdomainSummary):
    concepts: List[Dict[str, Any]] = []


class DomainSummary(BaseModel):
    id: str
    name: str
    description: str
    subdomain_count: int = 0


class DomainDetail(DomainSummary):
    subdomains: List[SubdomainSummary] = []


class DomainCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class DomainUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SubdomainCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    milestone_type: Optional[str] = None
    time_window_months: Optional[int] = None
    semantic_tags: List[str] = []


class SubdomainUpdateRequest(BaseModel):
    description: Optional[str] = None
    milestone_type: Optional[str] = None
    time_window_months: Optional[int] = None
    semantic_tags: Optional[List[str]] = None


class AddConceptRequest(BaseModel):
    concept_id: int
    term: str = Field(..., min_length=1)
    synonyms: List[str] = []


# ── Domain endpoints ─────────────────────────────────────────────────────


@router.get("/domains", response_model=List[DomainSummary])
def list_domains():
    """List all audit domains."""
    _ensure_default_domain()
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain) "
            "OPTIONAL MATCH (d)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "RETURN d.id AS id, d.name AS name, d.description AS description, "
            "count(v) AS subdomain_count "
            "ORDER BY d.name"
        )
        return [
            DomainSummary(
                id=r["id"],
                name=r["name"] or r["id"],
                description=r.get("description") or "",
                subdomain_count=r.get("subdomain_count", 0),
            )
            for r in rows
        ]
    finally:
        client.close()


@router.post("/domains", response_model=DomainSummary, status_code=201)
def create_domain(body: DomainCreateRequest):
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
            "CREATE (d:AuditDomain {id: $id, name: $name, description: $desc})",
            id=domain_id,
            name=body.name,
            desc=body.description,
        )
        return DomainSummary(
            id=domain_id,
            name=body.name,
            description=body.description,
            subdomain_count=0,
        )
    finally:
        client.close()


@router.get("/domains/{domain_id}", response_model=DomainDetail)
def get_domain(domain_id: str):
    """Get domain with its subdomains (reads flat properties, no JSON parsing)."""
    _ensure_default_domain()
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain {id: $id}) "
            "RETURN d.id AS id, d.name AS name, d.description AS description",
            id=domain_id,
        )
        if not rows:
            raise HTTPException(404, f"Domain '{domain_id}' not found")

        d = rows[0]

        vs_rows = client.run(
            "MATCH (d:AuditDomain {id: $id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "RETURN v.id AS vid, v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       v.rawJson AS rawJson "
            "ORDER BY v.name",
            id=domain_id,
        )

        subdomains: List[SubdomainSummary] = []
        for vr in vs_rows:
            subdomain_name = vr.get("name") or _valueset_id_to_subdomain(vr["vid"])
            tags = vr.get("semanticTags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, TypeError):
                    tags = []

            subdomains.append(SubdomainSummary(
                name=subdomain_name,
                description=vr.get("description") or "",
                milestone_type=vr.get("milestoneType"),
                time_window_months=vr.get("timeWindowMonths"),
                semantic_tags=tags,
                concept_count=_count_concepts_from_raw(vr.get("rawJson")),
            ))

        return DomainDetail(
            id=d["id"],
            name=d["name"] or d["id"],
            description=d.get("description") or "",
            subdomain_count=len(subdomains),
            subdomains=subdomains,
        )
    finally:
        client.close()


@router.put("/domains/{domain_id}", response_model=DomainSummary)
def update_domain(domain_id: str, body: DomainUpdateRequest):
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

        if sets:
            client.run(
                f"MATCH (d:AuditDomain {{id: $id}}) SET {', '.join(sets)}", **params
            )

        rows = client.run(
            "MATCH (d:AuditDomain {id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "RETURN d.id AS id, d.name AS name, d.description AS description, "
            "count(v) AS subdomain_count",
            id=domain_id,
        )
        r = rows[0]
        return DomainSummary(
            id=r["id"],
            name=r["name"] or r["id"],
            description=r.get("description") or "",
            subdomain_count=r.get("subdomain_count", 0),
        )
    finally:
        client.close()


@router.delete("/domains/{domain_id}", status_code=204)
def delete_domain(domain_id: str):
    """Delete an audit domain (does not delete subdomains/ValueSets)."""
    client = KnowledgeGraphClient()
    try:
        existing = client.run(
            "MATCH (d:AuditDomain {id: $id}) RETURN d.id AS id", id=domain_id
        )
        if not existing:
            raise HTTPException(404, f"Domain '{domain_id}' not found")
        client.run("MATCH (d:AuditDomain {id: $id}) DETACH DELETE d", id=domain_id)
    finally:
        client.close()


# ── Subdomain endpoints ──────────────────────────────────────────────────


@router.post(
    "/domains/{domain_id}/subdomains",
    response_model=SubdomainSummary,
    status_code=201,
)
def create_subdomain(domain_id: str, body: SubdomainCreateRequest):
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
        concept_count=0,
    )


@router.get(
    "/domains/{domain_id}/subdomains/{subdomain_name}",
    response_model=SubdomainDetail,
)
def get_subdomain(domain_id: str, subdomain_name: str):
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

    return SubdomainDetail(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=tags,
        concepts=_parse_concepts_from_raw(vr.get("rawJson")),
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


@router.put(
    "/domains/{domain_id}/subdomains/{subdomain_name}",
    response_model=SubdomainSummary,
)
def update_subdomain(
    domain_id: str, subdomain_name: str, body: SubdomainUpdateRequest
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

    DomainRegistry.reset_instance()

    return SubdomainSummary(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=tags,
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


# ── Concept endpoints (within a subdomain) ───────────────────────────────


@router.post(
    "/domains/{domain_id}/subdomains/{subdomain_name}/concepts",
    response_model=SubdomainDetail,
)
def add_concept(
    domain_id: str, subdomain_name: str, body: AddConceptRequest
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

    concepts.append({
        "code": str(body.concept_id),
        "display": body.term,
        "designation": designations,
    })

    _upsert_valueset_flat(vs_id, vs)
    DomainRegistry.reset_instance()

    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:ValueSet {id: $id}) "
            "RETURN v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       v.rawJson AS rawJson",
            id=vs_id,
        )
    finally:
        client.close()

    vr = rows[0]
    tags = vr.get("semanticTags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []

    return SubdomainDetail(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=tags,
        concepts=_parse_concepts_from_raw(vr.get("rawJson")),
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
    )


@router.delete(
    "/domains/{domain_id}/subdomains/{subdomain_name}/concepts/{concept_id}",
    response_model=SubdomainDetail,
)
def remove_concept(domain_id: str, subdomain_name: str, concept_id: str):
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
        rows = client.run(
            "MATCH (v:ValueSet {id: $id}) "
            "RETURN v.name AS name, v.description AS description, "
            "       v.milestoneType AS milestoneType, "
            "       v.timeWindowMonths AS timeWindowMonths, "
            "       v.semanticTags AS semanticTags, "
            "       v.rawJson AS rawJson",
            id=vs_id,
        )
    finally:
        client.close()

    vr = rows[0]
    tags = vr.get("semanticTags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []

    return SubdomainDetail(
        name=vr.get("name") or subdomain_name,
        description=vr.get("description") or "",
        milestone_type=vr.get("milestoneType"),
        time_window_months=vr.get("timeWindowMonths"),
        semantic_tags=tags,
        concepts=_parse_concepts_from_raw(vr.get("rawJson")),
        concept_count=_count_concepts_from_raw(vr.get("rawJson")),
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
