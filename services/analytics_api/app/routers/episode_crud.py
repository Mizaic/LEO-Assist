"""Manual EpisodeOfCare CRUD endpoints.

Atlas trace:
  DOs: DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205
  DIs: DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F, DI-41B71BF8, DI-3F61E3C5
  Risks: R-E951555E, R-DD23FB44, R-A737EE12
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0792E2CB")

Endpoints exposed under the ``/analytics`` prefix:

- ``POST   /episodes``                                      - manual create
- ``PATCH  /episodes/{episode_id}``                          - sparse update
- ``DELETE /episodes/{episode_id}``                          - hard delete
- ``POST   /episodes/{episode_id}/encounters``               - attach encounter
- ``DELETE /episodes/{episode_id}/encounters/{encounter_id}``- detach encounter

Each endpoint:

1. Resolves the caller scope via :func:`get_caller_scope`.
2. Enforces role gating via
   :func:`_episode_crud_helpers.require_eoc_curator_role` (mitigates
   R-E951555E, R-A737EE12).
3. Enforces org-scope via
   :func:`_episode_crud_helpers.require_episode_in_scope` /
   :func:`_require_patient_in_scope` (mitigates R-A737EE12).
4. Re-derives episode dates from the attached encounters via
   :func:`_episode_crud_helpers.recompute_episode_dates`
   (mitigates R-E951555E).
5. Writes a typed ``:AuditEvent`` row via
   :func:`_episode_crud_helpers.write_episode_audit_event`
   (mitigates R-A737EE12, R-DD23FB44).

The DELETE endpoint additionally requires the body's
``confirm_episode_id`` to equal the path ``episode_id`` (type-the-id
gate, mitigates R-DD23FB44).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

from ._episode_crud_helpers import (
    MILESTONE_TYPES,
    episode_property_snapshot,
    recompute_episode_dates,
    require_eoc_curator_role,
    require_episode_in_scope,
    write_episode_audit_event,
)

router = APIRouter()


def _coerce_scope(scope: CallerScope | object) -> CallerScope:
    """Mirror dashboards._coerce_scope so test stubs still work.

    Test fixtures sometimes inject a SimpleNamespace; FastAPI's
    Depends machinery returns a CallerScope in production. Anything
    that isn't already a CallerScope is wrapped as best-effort.
    """
    if isinstance(scope, CallerScope):
        return scope
    return CallerScope(
        email=getattr(scope, "email", "") or "",
        is_admin=bool(getattr(scope, "is_admin", False)),
        org_ids=list(getattr(scope, "org_ids", []) or []),
        scope_type=getattr(scope, "scope_type", None),
        primary_org_id=getattr(scope, "primary_org_id", None),
    )


class EpisodeEncounterAttachment(BaseModel):
    encounter_id: str
    milestone_type: str


class EpisodeCreateRequest(BaseModel):
    """Body for ``POST /episodes``.

    Mirrors the EditEpisodeDialog details panel.
    ``initial_encounter_links`` is optional; when present each entry
    is written as an ``IS_PART_OF`` edge tagged
    ``linked_by="manual_create"`` and the episode dates are
    re-derived from the resulting attachments.
    """

    patient_id: str
    cancer_type: Optional[str] = None
    condition_type: Optional[str] = None
    cancer_stage: Optional[str] = None
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = "in_review"
    audit_notes: Optional[str] = None
    audit_flag: Optional[str] = None
    initial_encounter_links: list[EpisodeEncounterAttachment] = []


class EpisodeUpdateRequest(BaseModel):
    """Sparse body for ``PATCH /episodes/{episode_id}``."""

    cancer_type: Optional[str] = None
    condition_type: Optional[str] = None
    cancer_stage: Optional[str] = None
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    inferred_outcome: Optional[str] = None
    audit_notes: Optional[str] = None
    audit_flag: Optional[str] = None


class EpisodeDeleteRequest(BaseModel):
    """Body for ``DELETE /episodes/{episode_id}``.

    The ``confirm_episode_id`` field MUST equal the path episode_id;
    otherwise the endpoint returns HTTP 400 before any graph write.
    """

    confirm_episode_id: str
    reason: Optional[str] = None


class EpisodeAttachEncounterRequest(BaseModel):
    encounter_id: str
    milestone_type: str


def _validate_milestone_type(value: str) -> None:
    if value not in MILESTONE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "milestone_type must be one of: "
                f"{sorted(MILESTONE_TYPES)}"
            ),
        )


def _require_patient_in_scope(
    client: PatientGraphClient,
    scope: CallerScope,
    patient_id: str,
) -> None:
    """Raise HTTP 404 when the patient is outside the caller's org_ids."""
    if scope.is_admin:
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "RETURN p.id AS id",
            pid=patient_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Patient not found")
        return
    rows = client.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "RETURN gp.id AS gp_id",
        pid=patient_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")
    gp_id = rows[0].get("gp_id")
    if gp_id not in scope.org_ids:
        raise HTTPException(status_code=404, detail="Patient not found")


def _create_episode_node(
    client: PatientGraphClient,
    body: EpisodeCreateRequest,
    scope: CallerScope,
    episode_id: str,
) -> None:
    """Helper: write the EpisodeOfCare node and its HAS_EPISODE_OF_CARE edge."""
    props = {
        "episode_id": episode_id,
        "cancer_type": body.cancer_type,
        "condition_type": body.condition_type or body.cancer_type,
        "cancer_stage": body.cancer_stage,
        "referral_date": body.referral_date,
        "end_date": body.end_date,
        "status": body.status or "in_review",
        "audit_notes": body.audit_notes or "",
        "audit_flag": body.audit_flag,
        "linked_by": "manual_create",
        "created_by": scope.email,
        "updated_by": scope.email,
        "needs_review": True,
    }
    client.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "CREATE (ep:EpisodeOfCare) "
        "SET ep += $props, "
        "    ep.created_at = datetime(), "
        "    ep.updated_at = datetime() "
        "MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep) "
        "RETURN ep.episode_id AS episode_id",
        pid=body.patient_id,
        props={k: v for k, v in props.items() if v is not None},
    )


def _link_initial_encounters(
    client: PatientGraphClient,
    episode_id: str,
    links: list[EpisodeEncounterAttachment],
) -> None:
    for link in links:
        client.run(
            "MATCH (e:Encounter {id: $enc}) "
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
            "MERGE (e)-[r:IS_PART_OF]->(ep) "
            "SET r.milestone_type = $mt, "
            "    r.linked_by = 'manual_create', "
            "    r.linked_at = datetime()",
            enc=link.encounter_id,
            eid=episode_id,
            mt=link.milestone_type,
        )


@router.post("/episodes")
def create_episode(
    body: EpisodeCreateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Manually create an EpisodeOfCare from the patient drawer."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    if not body.patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")
    for link in body.initial_encounter_links:
        _validate_milestone_type(link.milestone_type)

    episode_id = f"ep-manual-{uuid.uuid4().hex[:12]}"
    client = PatientGraphClient()
    try:
        _require_patient_in_scope(client, scope, body.patient_id)
        _create_episode_node(client, body, scope, episode_id)
        _link_initial_encounters(
            client, episode_id, body.initial_encounter_links
        )
        derived_dates: Optional[dict] = None
        if body.initial_encounter_links and not (
            body.referral_date and body.end_date
        ):
            derived_dates = recompute_episode_dates(client, episode_id)
        after_snapshot = episode_property_snapshot(client, episode_id)
        write_episode_audit_event(
            client,
            event_type="EpisodeManualCreate",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=body.patient_id,
            before=None,
            after=after_snapshot,
            notes=body.audit_notes or "",
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "patient_id": body.patient_id,
            "derived_dates": derived_dates,
        }
    finally:
        client.close()


@router.patch("/episodes/{episode_id}")
def update_episode(
    episode_id: str,
    body: EpisodeUpdateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Sparse patch on EpisodeOfCare properties from the patient drawer."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)

    raw_patch = body.model_dump(exclude_unset=True)
    if not raw_patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        before = episode_property_snapshot(client, episode_id)
        set_fragments = [f"ep.{key} = ${key}" for key in raw_patch]
        set_clause = ", ".join(set_fragments)
        client.run(
            f"MATCH (ep:EpisodeOfCare {{episode_id: $eid}}) "
            f"SET {set_clause}, "
            "    ep.updated_by = $updated_by, "
            "    ep.updated_at = datetime() "
            "RETURN ep.episode_id AS episode_id",
            eid=episode_id,
            updated_by=scope.email or "",
            **raw_patch,
        )
        after = episode_property_snapshot(client, episode_id)
        write_episode_audit_event(
            client,
            event_type="EpisodeManualUpdate",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=after,
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "updated_fields": sorted(raw_patch.keys()),
        }
    finally:
        client.close()


@router.delete("/episodes/{episode_id}")
def delete_episode(
    episode_id: str,
    body: EpisodeDeleteRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Hard-delete an EpisodeOfCare with a type-the-id confirm gate."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    if body.confirm_episode_id != episode_id:
        raise HTTPException(
            status_code=400,
            detail="confirm_episode_id must equal the path episode_id.",
        )
    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        before = episode_property_snapshot(client, episode_id)
        client.run(
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) DETACH DELETE ep",
            eid=episode_id,
        )
        write_episode_audit_event(
            client,
            event_type="EpisodeManualDelete",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=None,
            notes=body.reason or "",
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "patient_id": patient_id,
        }
    finally:
        client.close()


@router.post("/episodes/{episode_id}/encounters")
def attach_encounter_to_episode(
    episode_id: str,
    body: EpisodeAttachEncounterRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Attach an Encounter to an EpisodeOfCare with a milestone slot."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    _validate_milestone_type(body.milestone_type)
    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        before = episode_property_snapshot(client, episode_id)
        result = client.run(
            "MATCH (e:Encounter {id: $enc}) "
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
            "MERGE (e)-[r:IS_PART_OF]->(ep) "
            "SET r.milestone_type = $mt, "
            "    r.linked_by = 'manual_attach', "
            "    r.linked_at = datetime() "
            "RETURN e.id AS encounter_id",
            enc=body.encounter_id,
            eid=episode_id,
            mt=body.milestone_type,
        )
        if not result:
            raise HTTPException(
                status_code=404, detail="Encounter or episode not found"
            )
        derived = recompute_episode_dates(client, episode_id)
        after = episode_property_snapshot(client, episode_id)
        write_episode_audit_event(
            client,
            event_type="EpisodeManualAttach",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=after,
            notes=(
                f"Attached encounter={body.encounter_id} "
                f"as milestone={body.milestone_type}"
            ),
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "encounter_id": body.encounter_id,
            "milestone_type": body.milestone_type,
            "derived_dates": derived,
        }
    finally:
        client.close()


@router.delete("/episodes/{episode_id}/encounters/{encounter_id}")
def detach_encounter_from_episode(
    episode_id: str,
    encounter_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Detach an Encounter from an EpisodeOfCare."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        before = episode_property_snapshot(client, episode_id)
        result = client.run(
            "MATCH (e:Encounter {id: $enc})-[r:IS_PART_OF]->"
            "(ep:EpisodeOfCare {episode_id: $eid}) "
            "WITH r, e.id AS encounter_id "
            "DELETE r "
            "RETURN encounter_id",
            enc=encounter_id,
            eid=episode_id,
        )
        if not result:
            raise HTTPException(
                status_code=404,
                detail="No IS_PART_OF edge between encounter and episode",
            )
        derived = recompute_episode_dates(client, episode_id)
        after = episode_property_snapshot(client, episode_id)
        write_episode_audit_event(
            client,
            event_type="EpisodeManualDetach",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=after,
            notes=f"Detached encounter={encounter_id}",
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "encounter_id": encounter_id,
            "derived_dates": derived,
        }
    finally:
        client.close()
