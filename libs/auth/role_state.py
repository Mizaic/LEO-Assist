"""Role state helpers for the Wave D role-first shell.

Reads and writes Practitioner.selected_role + allowed_roles, and emits an
append-only (:RoleSwitch) audit node on every switch. See DI-LEO-AI-129.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from libs.cypher.role_queries import (
    CANONICAL_ROLES,
    CREATE_ROLE_SWITCH_AUDIT,
    GET_PRACTITIONER_ROLE_STATE,
    SET_PRACTITIONER_SELECTED_ROLE,
)
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


@dataclass
class RoleState:
    selected_role: str | None
    allowed_roles: list[str]


class RoleNotAllowedError(PermissionError):
    """Raised when a user tries to select a role they do not have."""


def _canonical(roles: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in roles:
        if not isinstance(r, str):
            continue
        if r not in CANONICAL_ROLES:
            continue
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


def fetch_role_state(email: str) -> RoleState:
    """Return the current role state for the given practitioner.

    On any graph error or missing Practitioner, returns an empty state so the
    shell can fall back to the legacy nav (see R-LEO-AI-089 mitigation).
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        return RoleState(selected_role=None, allowed_roles=[])
    client = PatientGraphClient()
    try:
        rows = client.run(GET_PRACTITIONER_ROLE_STATE, email=normalized)
        if not rows:
            return RoleState(selected_role=None, allowed_roles=[])
        row = rows[0]
        allowed = _canonical(row.get("allowed_roles") or [])
        selected_raw = row.get("selected_role")
        selected = selected_raw if selected_raw in allowed else None
        return RoleState(selected_role=selected, allowed_roles=allowed)
    except Exception as exc:
        logger.warning("role_state.fetch_failed email=%s err=%s", normalized, exc)
        return RoleState(selected_role=None, allowed_roles=[])
    finally:
        client.close()


def set_selected_role(
    email: str,
    new_role: str,
    session_id: str,
) -> RoleState:
    """Set the selected role and write a (:RoleSwitch) audit node.

    Raises RoleNotAllowedError if the target role is not in the
    practitioner's HAS_ROLE set.
    """
    normalized = (email or "").strip().lower()
    if not normalized:
        raise RoleNotAllowedError("missing_email")
    current = fetch_role_state(normalized)
    if new_role not in current.allowed_roles:
        raise RoleNotAllowedError(new_role)

    now = datetime.now(timezone.utc).isoformat()
    audit_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        client.run(
            CREATE_ROLE_SWITCH_AUDIT,
            email=normalized,
            audit_id=audit_id,
            from_role=current.selected_role or "",
            to_role=new_role,
            at=now,
            session_id=session_id,
        )
        rows = client.run(
            SET_PRACTITIONER_SELECTED_ROLE,
            email=normalized,
            role=new_role,
        )
        if not rows:
            logger.warning(
                "role_state.set_failed email=%s role=%s",
                normalized,
                new_role,
            )
            return current
        row = rows[0]
        allowed = _canonical(row.get("allowed_roles") or [])
        selected = row.get("selected_role")
        if selected not in allowed:
            selected = None
        return RoleState(selected_role=selected, allowed_roles=allowed)
    finally:
        client.close()
