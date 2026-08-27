"""Resolve receiving Service scope for Elective SPoA referral assessment.

Uses the existing patient-graph schema:
  ReferralRequest|CommunicationRequest -[:FOR_SERVICE]-> Service
  ReferralRequest|CommunicationRequest -[:IN_WORKFLOW]-> Workflow -[:FOR_SERVICE]-> Service
  Service -[:PROVIDES_SERVICE_FOR]-> Organization
  Service -[:USES_GUIDANCE]-> Guideline|Guidance

Atlas trace:
  DO: DO-EBD03C23
  DI: DI-5133534D
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_RESOLVE_CYPHER = """
MATCH (src {id: $source_id})
WHERE $source_label IN labels(src)
OPTIONAL MATCH (src)-[:FOR_SERVICE]->(s:Service)
OPTIONAL MATCH (src)-[:IN_WORKFLOW]->(:Workflow)-[:FOR_SERVICE]->(s2:Service)
WITH coalesce(s, s2) AS svc
WHERE svc IS NOT NULL
OPTIONAL MATCH (svc)-[:PROVIDES_SERVICE_FOR]->(org:Organization)
OPTIONAL MATCH (svc)-[:USES_GUIDANCE]->(g)
RETURN svc.id AS id,
       svc.name AS name,
       coalesce(svc.ers_service_id, svc.id) AS ers_service_id,
       coalesce(svc.specialty, svc.clinicalType, '') AS specialty,
       svc.guideline_ids AS guideline_ids_prop,
       collect(DISTINCT g.id) AS guidance_ids,
       svc.completeness_domain AS completeness_domain,
       svc.completeness_subdomain AS completeness_subdomain,
       svc.spoa_id AS spoa_id,
       org.id AS organization_id,
       coalesce(org.name, org.short_name, org.id, '') AS organization_name
LIMIT 1
"""


@dataclass(frozen=True)
class HealthcareServiceScope:
    """Receiving :Service linked from a referral or A&G request."""

    id: str
    name: str
    specialty: str
    guideline_ids: list[str]
    completeness_domain: str | None = None
    completeness_subdomain: str | None = None
    spoa_id: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None
    ers_service_id: str | None = None


def _normalise_guideline_ids(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    return [text] if text else []


def _merge_guideline_ids(prop_raw: Any, guidance_ids: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in _normalise_guideline_ids(prop_raw):
        if item not in seen:
            seen.add(item)
            merged.append(item)
    for item in guidance_ids or []:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            merged.append(text)
    return merged


def _row_to_scope(row: dict[str, Any]) -> HealthcareServiceScope | None:
    service_id = str(row.get("id") or "").strip()
    if not service_id:
        return None
    return HealthcareServiceScope(
        id=service_id,
        name=str(row.get("name") or service_id).strip(),
        specialty=str(row.get("specialty") or "").strip(),
        guideline_ids=_merge_guideline_ids(
            row.get("guideline_ids_prop"),
            row.get("guidance_ids"),
        ),
        completeness_domain=str(row.get("completeness_domain") or "").strip() or None,
        completeness_subdomain=(
            str(row.get("completeness_subdomain") or "").strip() or None
        ),
        spoa_id=str(row.get("spoa_id") or "").strip() or None,
        organization_id=str(row.get("organization_id") or "").strip() or None,
        organization_name=str(row.get("organization_name") or "").strip() or None,
        ers_service_id=str(row.get("ers_service_id") or "").strip() or None,
    )


def resolve_healthcare_service(
    client: Any,
    *,
    source_node_type: str,
    source_node_id: str,
) -> HealthcareServiceScope | None:
    """Load the receiving Service for a referral or A&G source node."""
    source_id = str(source_node_id or "").strip()
    source_label = str(source_node_type or "").strip()
    if not source_id or not source_label:
        return None
    rows = client.run(
        _RESOLVE_CYPHER,
        source_id=source_id,
        source_label=source_label,
    )
    if not rows:
        return None
    return _row_to_scope(rows[0])


def apply_healthcare_service_scope(
    state: dict[str, Any],
    service: HealthcareServiceScope | None,
    *,
    message_guideline_ids: list[str] | None = None,
) -> None:
    """Write receiving-service fields and resolved guideline scope onto state."""
    override_ids = [
        str(item).strip() for item in (message_guideline_ids or []) if str(item).strip()
    ]
    if service is None:
        state["healthcare_service_missing"] = True
        if override_ids:
            state["primary_guideline_ids"] = list(override_ids)
            state["guideline_scope_type"] = "guideline"
            state["guideline_scope_id"] = override_ids[0]
            state["guideline_id"] = override_ids[0]
            state["guideline_ids"] = list(override_ids)
        return

    state["healthcare_service_id"] = service.id
    state["healthcare_service_name"] = service.name
    if service.ers_service_id:
        state["healthcare_service_ers_id"] = service.ers_service_id
    state["healthcare_service_specialty"] = service.specialty
    state["healthcare_service_spoa_id"] = service.spoa_id
    state["healthcare_service_missing"] = False
    if service.organization_id:
        state["healthcare_service_org_id"] = service.organization_id
    if service.organization_name:
        state["healthcare_service_org_name"] = service.organization_name

    primary_ids = list(override_ids or service.guideline_ids)
    state["primary_guideline_ids"] = primary_ids
    if primary_ids:
        state["guideline_scope_type"] = "guideline"
        state["guideline_scope_id"] = primary_ids[0]
        state["guideline_id"] = primary_ids[0]
        state["guideline_ids"] = list(primary_ids)
    if not state.get("completeness_domain") and service.completeness_domain:
        state["completeness_domain"] = service.completeness_domain
    if not state.get("completeness_subdomain") and service.completeness_subdomain:
        state["completeness_subdomain"] = service.completeness_subdomain
