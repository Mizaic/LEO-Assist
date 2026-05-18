"""Manual EpisodeOfCare CRUD endpoints.

Atlas trace: DOs DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205,
DO-128CB534 (multi-slot); DIs DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F,
DI-41B71BF8, DI-3F61E3C5, DI-F5E030ED (multi-slot); Risks
R-E951555E, R-DD23FB44, R-A737EE12.

Endpoints under the /analytics prefix:
- POST   /episodes                                       -- manual create
- PATCH  /episodes/{episode_id}                          -- sparse update
- DELETE /episodes/{episode_id}                          -- hard delete
- POST   /episodes/{episode_id}/encounters               -- attach encounter (multi-slot)
- DELETE /episodes/{episode_id}/encounters/{encounter_id}-- per-slot or bulk detach

Each endpoint resolves caller scope, enforces role gating
(require_eoc_curator_role -> R-E951555E, R-A737EE12) and org-scope
(require_episode_in_scope, _require_patient_in_scope -> R-A737EE12),
re-derives episode dates (recompute_episode_dates -> R-E951555E) and
writes a typed :AuditEvent (write_episode_audit_event -> R-A737EE12,
R-DD23FB44). DELETE requires confirm_episode_id == episode_id
(type-the-id gate -> R-DD23FB44)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.episodes.status import EpisodeStatus
from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

from ._episode_crud_helpers import (
    MILESTONE_TYPES,
    encounter_slot_edge_exists,
    episode_property_snapshot,
    recompute_episode_dates,
    recompute_episode_status,
    require_eoc_curator_role,
    require_episode_in_scope,
    write_episode_audit_event,
)

router = APIRouter()


def _coerce_scope(scope: CallerScope | object) -> CallerScope:
    """Mirror dashboards._coerce_scope so SimpleNamespace test stubs work."""
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
    """Body for POST /episodes; mirrors the EditEpisodeDialog details
    panel. ``initial_encounter_links`` entries are written as
    :IS_PART_OF edges tagged ``linked_by='manual_create'`` and dates
    re-derived."""

    patient_id: str
    cancer_type: Optional[str] = None
    condition_type: Optional[str] = None
    cancer_stage: Optional[str] = None
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    # Default to the canonical EpisodeStatus.REVIEW value rather than
    # the legacy "in_review" string. The contract test in
    # tests/contracts/test_episode_status_vocabulary.py rejects
    # "in_review" as an out-of-vocabulary writer literal.
    status: str = EpisodeStatus.REVIEW.value
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
    """Body for DELETE /episodes/{episode_id}; confirm_episode_id MUST
    equal the path episode_id or endpoint returns HTTP 400."""

    confirm_episode_id: str
    reason: Optional[str] = None


class EpisodeAttachEncounterRequest(BaseModel):
    encounter_id: str
    milestone_type: str
    correction_target: Optional[str] = None


def _validate_milestone_type(value: str) -> None:
    if value not in MILESTONE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=("milestone_type must be one of: " f"{sorted(MILESTONE_TYPES)}"),
        )


def _normalise_optional_cancer_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return normalise_cancer_type(value)


def _require_patient_in_scope(
    client: PatientGraphClient,
    scope: CallerScope,
    patient_id: str,
) -> None:
    """Raise HTTP 404 when the patient is outside the caller's org_ids."""
    if scope.is_admin:
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid " "RETURN p.id AS id",
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
    """Helper: write the EpisodeOfCare node and its HAS_EPISODE_OF_CARE edge.

    Writes both legacy ``needs_review`` and canonical
    ``needs_human_review`` so the v2 detector and the dashboard
    cannot drift between two parallel review-flag fields
    (DI-C4CEFA32). Defaults the status to canonical
    ``EpisodeStatus.REVIEW`` when the request body omits it.
    """
    canonical_status = body.status or EpisodeStatus.REVIEW.value
    cancer_type = _normalise_optional_cancer_type(body.cancer_type)
    condition_type = _normalise_optional_cancer_type(
        body.condition_type or body.cancer_type
    )
    props = {
        "episode_id": episode_id,
        "cancer_type": cancer_type,
        "condition_type": condition_type,
        "cancer_stage": body.cancer_stage,
        "referral_date": body.referral_date,
        "end_date": body.end_date,
        "status": canonical_status,
        "audit_notes": body.audit_notes or "",
        "audit_flag": body.audit_flag,
        "linked_by": "manual_create",
        "created_by": scope.email,
        "updated_by": scope.email,
        "needs_review": True,
        "needs_human_review": True,
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
    """MERGE keys on milestone_type so one encounter can hold multiple
    slots (DI-F5E030ED); aligns with AI engine writer."""
    for link in links:
        client.run(
            "MATCH (e:Encounter {id: $enc}) "
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
            "MERGE (e)-[r:IS_PART_OF {milestone_type: $mt}]->(ep) "
            "ON CREATE SET r.linked_by = 'manual_create', "
            "              r.linked_at = datetime()",
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
        _link_initial_encounters(client, episode_id, body.initial_encounter_links)
        derived_dates: Optional[dict] = None
        if body.initial_encounter_links and not (body.referral_date and body.end_date):
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
    if "cancer_type" in raw_patch:
        raw_patch["cancer_type"] = _normalise_optional_cancer_type(
            raw_patch["cancer_type"]
        )
    if "condition_type" in raw_patch:
        raw_patch["condition_type"] = _normalise_optional_cancer_type(
            raw_patch["condition_type"]
        )
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
    """Attach an Encounter to an EpisodeOfCare under a milestone slot.

    MERGE keys on (encounter_id, episode_id, milestone_type) so one
    encounter can fill multiple slots on the same episode
    (DI-F5E030ED). Idempotent re-MERGE returns already_linked=true
    with no AuditEvent."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    _validate_milestone_type(body.milestone_type)
    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        # Short-circuit idempotent re-MERGE (DI-F5E030ED).
        if encounter_slot_edge_exists(
            client, body.encounter_id, episode_id, body.milestone_type
        ):
            return {
                "success": True,
                "already_linked": True,
                "episode_id": episode_id,
                "encounter_id": body.encounter_id,
                "milestone_type": body.milestone_type,
                "derived_dates": None,
            }
        before = episode_property_snapshot(client, episode_id)
        result = client.run(
            "MATCH (e:Encounter {id: $enc}) "
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
            "MERGE (e)-[r:IS_PART_OF {milestone_type: $mt}]->(ep) "
            "ON CREATE SET r.linked_by = 'manual_attach', "
            "              r.linked_at = datetime() "
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
        # Recompute the engine-equivalent status if the slot just
        # attached pushes the pathway into a closure / diagnosis
        # state. Without this the rail and the cohort filters stay
        # stuck on "active" / "in_review" until the next pipeline
        # run, which surprises curators (DI-3A19BE12).
        status_change = recompute_episode_status(client, episode_id)
        after = episode_property_snapshot(client, episode_id)
        attach_note = (
            f"Attached encounter={body.encounter_id} "
            f"as milestone={body.milestone_type}"
        )
        if status_change.get("changed"):
            attach_note += (
                f"; status {status_change['previous_status']} "
                f"-> {status_change['status']}"
            )
        write_episode_audit_event(
            client,
            event_type="EpisodeManualAttach",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=after,
            notes=attach_note,
            correction_target=body.correction_target or "detector_boundary",
        )
        return {
            "success": True,
            "already_linked": False,
            "episode_id": episode_id,
            "encounter_id": body.encounter_id,
            "milestone_type": body.milestone_type,
            "derived_dates": derived,
            "status_change": status_change,
        }
    finally:
        client.close()


@router.delete("/episodes/{episode_id}/encounters/{encounter_id}")
def detach_encounter_from_episode(
    episode_id: str,
    encounter_id: str,
    milestone_type: Optional[str] = None,
    correction_target: Optional[str] = None,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Detach an Encounter from an EpisodeOfCare.

    Per-slot detach (DI-F5E030ED): ``milestone_type`` present removes
    just that edge; omitted removes every :IS_PART_OF edge between
    the pair (legacy / CLI behaviour).

    Detach is intentionally permissive about ``milestone_type``: the
    value is just a property match key for an edge that already
    exists in the graph, so legacy slot values that pre-date the
    canonical vocabulary (e.g. ``presentation``, ``first_clinic``,
    ``first_clinic_visit``, ``treatment_decision``, ``specialist_visit``)
    can still be removed by a curator. If the value does not match an
    existing edge the Cypher returns no rows and we 404. Validation
    stays strict on the attach path so new edges only ever use
    canonical types (DI-F5E030ED, DI-50C7E89C)."""
    scope = _coerce_scope(scope)
    actor_role = require_eoc_curator_role(scope)
    client = PatientGraphClient()
    try:
        patient_id = require_episode_in_scope(client, scope, episode_id)
        before = episode_property_snapshot(client, episode_id)
        if milestone_type is None:
            result = client.run(
                "MATCH (e:Encounter {id: $enc})-[r:IS_PART_OF]->"
                "(ep:EpisodeOfCare {episode_id: $eid}) "
                "WITH r, e.id AS encounter_id "
                "DELETE r "
                "RETURN encounter_id",
                enc=encounter_id,
                eid=episode_id,
            )
            detach_note = f"Detached encounter={encounter_id} (all slots)"
        else:
            result = client.run(
                "MATCH (e:Encounter {id: $enc})-"
                "[r:IS_PART_OF {milestone_type: $mt}]->"
                "(ep:EpisodeOfCare {episode_id: $eid}) "
                "WITH r, e.id AS encounter_id "
                "DELETE r "
                "RETURN encounter_id",
                enc=encounter_id,
                eid=episode_id,
                mt=milestone_type,
            )
            detach_note = (
                f"Detached encounter={encounter_id} " f"from slot={milestone_type}"
            )
        if not result:
            raise HTTPException(
                status_code=404,
                detail="No IS_PART_OF edge between encounter and episode",
            )
        derived = recompute_episode_dates(client, episode_id)
        # Detaching a closure / diagnosis slot reopens the pathway;
        # the helper handles the revert from completed / closed_benign
        # back to active when the relevant slot is gone (DI-3A19BE12).
        status_change = recompute_episode_status(client, episode_id)
        after = episode_property_snapshot(client, episode_id)
        if status_change.get("changed"):
            detach_note += (
                f"; status {status_change['previous_status']} "
                f"-> {status_change['status']}"
            )
        write_episode_audit_event(
            client,
            event_type="EpisodeManualDetach",
            actor_email=scope.email or "",
            actor_role=actor_role,
            episode_id=episode_id,
            patient_id=patient_id or None,
            before=before,
            after=after,
            notes=detach_note,
            correction_target=correction_target or "detector_boundary",
        )
        return {
            "success": True,
            "episode_id": episode_id,
            "encounter_id": encounter_id,
            "milestone_type": milestone_type,
            "derived_dates": derived,
            "status_change": status_change,
        }
    finally:
        client.close()
