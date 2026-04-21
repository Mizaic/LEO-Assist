"""Shared helpers for the manual EpisodeOfCare CRUD endpoints.

Atlas trace:
  DOs: DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205
  DIs: DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F, DI-41B71BF8
  Risks: R-E951555E, R-DD23FB44, R-A737EE12
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0792E2CB")

Provides:

- ``EOC_CURATOR_ROLES`` - the set of selected_role values allowed to mutate
  EpisodeOfCare nodes via the manual CRUD endpoints
  (mitigation for R-E951555E, R-A737EE12).
- ``require_eoc_curator_role`` - role gate raising HTTP 403 when the caller
  is not in ``EOC_CURATOR_ROLES``. Admin scopes always pass.
- ``require_episode_in_scope`` - org-scope gate raising HTTP 404 when the
  episode's patient is outside the caller's org_ids; returns the patient id.
- ``recompute_episode_dates`` - re-derive ``referral_date`` / ``end_date`` /
  ``diagnostic_interval_days`` / ``primary_care_interval_days`` from the
  current attached encounters (mitigation for R-E951555E).
- ``write_episode_audit_event`` - create an ``:AuditEvent`` row tagged
  ``EpisodeManual<verb>`` linked to the patient via ``AUDIT_FOR``
  (mitigation for R-A737EE12).
- ``MILESTONE_TYPES`` - canonical milestone enum reused from
  ``edit_milestone`` so attach / detach validate the same set.

Kept in its own module so dashboards.py stays under the 500 LOC hard limit.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import HTTPException

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

# Roles allowed to create / update / delete / link EpisodeOfCare nodes
# from the Mission Control patient drawer. Mirrors the front-end role
# gate in PatientDetailDrawer / EditEpisodeDialog.
EOC_CURATOR_ROLES: frozenset[str] = frozenset(
    {"clinician", "qa_ra_lead", "platform_admin"}
)

# Milestone enum reused by edit_milestone (services/analytics_api/app/
# routers/dashboards.py::edit_milestone). Kept in sync deliberately --
# attach / detach must validate the same set.
MILESTONE_TYPES: frozenset[str] = frozenset(
    {
        "first_presentation",
        "presentation",
        "referral",
        "referral_sent",
        "specialist_visit",
        "first_clinic_visit",
        "clinic_visit",
        "first_clinic",
        "investigation",
        "diagnosis",
        "diagnosis_confirmed",
        "treatment_decision",
        "treatment",
        "treatment_started",
        "first_treatment",
        "related",
    }
)

_REFERRAL_MILESTONES = {"referral", "referral_sent", "first_presentation"}
_PRESENTATION_MILESTONES = {
    "first_presentation",
    "presentation",
}
_DIAGNOSIS_MILESTONES = {"diagnosis", "diagnosis_confirmed"}
_TREATMENT_MILESTONES = {
    "treatment",
    "treatment_started",
    "first_treatment",
    "treatment_decision",
}


def require_eoc_curator_role(scope: CallerScope) -> str:
    """Raise HTTP 403 if the caller cannot mutate EpisodeOfCare nodes.

    Admin scopes (``scope.is_admin``) always pass and report the actor
    role as ``platform_admin``. For non-admin callers the function
    consults ``libs.auth.role_state.fetch_role_state`` and requires the
    practitioner's currently selected role to be in
    :data:`EOC_CURATOR_ROLES`.

    Returns the effective actor role string (used by audit writes).
    """
    if scope.is_admin:
        return "platform_admin"
    if not scope.email:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Lazy import to avoid pulling Redis / Neo4j role helpers into
    # dashboards.py module-import time during cold starts.
    from libs.auth.role_state import fetch_role_state

    role_state = fetch_role_state(scope.email)
    selected = role_state.selected_role
    if selected not in EOC_CURATOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "Selected role is not authorised to edit episodes of care. "
                "Allowed roles: clinician, qa_ra_lead, platform_admin."
            ),
        )
    return selected


def require_episode_in_scope(
    client: PatientGraphClient,
    scope: CallerScope,
    episode_id: str,
) -> str:
    """Return the owning patient_id, raising HTTP 404 when out of scope.

    Mirrors the gp.id check used by the existing close / merge / edit_milestone
    endpoints. Admin scopes skip the org_ids check but still require the
    episode to exist.
    """
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->"
        "(ep:EpisodeOfCare {episode_id: $eid}) "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "RETURN toString(p.id) AS patient_id, gp.id AS gp_id",
        eid=episode_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Episode not found")
    row = rows[0]
    patient_id = row.get("patient_id")
    if not scope.is_admin:
        gp_id = row.get("gp_id")
        if gp_id not in scope.org_ids:
            raise HTTPException(status_code=404, detail="Episode not found")
    return str(patient_id) if patient_id else ""


def recompute_episode_dates(
    client: PatientGraphClient,
    episode_id: str,
) -> dict:
    """Re-derive episode date fields from the current attached encounters.

    Sets:

    - ``referral_date`` = min(date of attached referral / first-presentation
      milestones) when present, otherwise null.
    - ``end_date`` = max(date of attached treatment-class milestones) when
      present, otherwise null.
    - ``diagnostic_interval_days`` = days(min diagnosis date - referral_date)
      when both anchors exist, otherwise null.
    - ``primary_care_interval_days`` = days(referral_date - min presentation
      date) when both anchors exist, otherwise null.

    Mirrors the convention used by libs/episode_engine builder so manual
    attach / detach cannot drift the derived date fields away from the
    underlying encounter evidence (mitigation for R-E951555E).
    """
    rows = client.run(
        "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
        "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
        "WHERE r.milestone_type IS NOT NULL "
        "WITH ep, collect({mt: r.milestone_type, "
        "                  d: toString(e.date)}) AS slots "
        "RETURN ep.episode_id AS episode_id, slots",
        eid=episode_id,
    )
    if not rows:
        return {
            "referral_date": None,
            "end_date": None,
            "diagnostic_interval_days": None,
            "primary_care_interval_days": None,
        }
    slots = rows[0].get("slots") or []

    def _min_date(types: Iterable[str]) -> Optional[str]:
        candidates = [
            s["d"]
            for s in slots
            if s and s.get("mt") in types and s.get("d")
        ]
        return min(candidates) if candidates else None

    def _max_date(types: Iterable[str]) -> Optional[str]:
        candidates = [
            s["d"]
            for s in slots
            if s and s.get("mt") in types and s.get("d")
        ]
        return max(candidates) if candidates else None

    referral_date = _min_date(_REFERRAL_MILESTONES)
    presentation_date = _min_date(_PRESENTATION_MILESTONES)
    diagnosis_date = _min_date(_DIAGNOSIS_MILESTONES)
    end_date = _max_date(_TREATMENT_MILESTONES)

    diagnostic_interval = _date_diff_days(referral_date, diagnosis_date)
    primary_care_interval = _date_diff_days(presentation_date, referral_date)

    client.run(
        "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
        "SET ep.referral_date = $referral_date, "
        "    ep.end_date = $end_date, "
        "    ep.diagnostic_interval_days = $diagnostic_interval_days, "
        "    ep.primary_care_interval_days = $primary_care_interval_days, "
        "    ep.dates_updated_at = datetime()",
        eid=episode_id,
        referral_date=referral_date,
        end_date=end_date,
        diagnostic_interval_days=diagnostic_interval,
        primary_care_interval_days=primary_care_interval,
    )
    return {
        "referral_date": referral_date,
        "end_date": end_date,
        "diagnostic_interval_days": diagnostic_interval,
        "primary_care_interval_days": primary_care_interval,
    }


def _date_diff_days(start: Optional[str], end: Optional[str]) -> Optional[int]:
    if not start or not end:
        return None
    try:
        s = datetime.fromisoformat(start[:10])
        e = datetime.fromisoformat(end[:10])
    except ValueError:
        return None
    return (e - s).days


def write_episode_audit_event(
    client: PatientGraphClient,
    event_type: str,
    actor_email: str,
    actor_role: str,
    episode_id: str,
    patient_id: Optional[str],
    before: Optional[dict],
    after: Optional[dict],
    notes: Optional[str] = None,
) -> str:
    """Create an ``:AuditEvent`` row for a manual EoC mutation.

    Stores the actor (email + role), the affected ``episode_id`` and the
    ``before`` / ``after`` property snapshots as JSON strings so the QA /
    RA lead can reconstruct any change. When ``patient_id`` is supplied
    an ``(:AuditEvent)-[:AUDIT_FOR]->(:Patient)`` edge is created so the
    Mission Control audit trail tab surfaces the event.

    Returns the new AuditEvent id.
    """
    audit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    props = {
        "id": audit_id,
        "type": event_type,
        "subtype": "episode_manual_edit",
        "actor_email": actor_email or "",
        "actor_role": actor_role or "",
        "episode_id": episode_id,
        "patient_id": patient_id or "",
        "before_json": _safe_json(before),
        "after_json": _safe_json(after),
        "notes": notes or "",
        "created_at_iso": now,
    }
    client.run(
        "CREATE (ae:AuditEvent) "
        "SET ae += $props, "
        "    ae.created_at = datetime($now)",
        props=props,
        now=now,
    )
    if patient_id:
        client.run(
            "MATCH (ae:AuditEvent {id: $aid}) "
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "MERGE (ae)-[:AUDIT_FOR]->(p)",
            aid=audit_id,
            pid=patient_id,
        )
    return audit_id


def _safe_json(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def episode_property_snapshot(
    client: PatientGraphClient,
    episode_id: str,
) -> Optional[dict]:
    """Return the full property map of an EpisodeOfCare for audit snapshots.

    Returns None when the episode does not exist.
    """
    rows = client.run(
        "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
        "RETURN properties(ep) AS props",
        eid=episode_id,
    )
    if not rows:
        return None
    raw = rows[0].get("props") or {}
    return {k: _coerce_scalar(v) for k, v in raw.items()}


def _coerce_scalar(value: Any) -> Any:
    """Coerce Neo4j temporal / list types to JSON-safe primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_coerce_scalar(v) for v in value]
    return str(value)
