"""Durable structured security audit log (GAP-012).

Every call to emit_* writes a single-line JSON record to the
'security.audit' logger at WARNING level so it is always emitted
regardless of the application's default log level.

A production deployment should configure this logger with a handler
that writes to an append-only destination: Azure Monitor / Log Analytics
(via the AzureMonitorLogExporter or a Log Analytics workspace data
connector), a write-once Azure Blob container, or a SIEM.

Event taxonomy
--------------
auth.login.success      -- OAuth callback completed, session created
auth.login.failure      -- Token verification failed or user rejected
auth.login.mfa_blocked  -- Login blocked due to missing MFA
auth.logout             -- Explicit logout, session deleted
auth.session.expired    -- Session not found in Redis (implicit expiry)
auth.entra_groups.resolved      -- Entra `groups` claim resolved to LEO roles at login
auth.entra_groups.missing       -- Token had no `groups` claim, fallthrough to existing edges
auth.entra_groups.overage       -- Token presented overage indicator, fallthrough to existing edges
auth.entra_groups.unknown_group -- A group object ID in the claim does not match any :Group node
authz.denied            -- require_admin or require_scope raised 403/401
authz.admin_action      -- Privileged mutation executed by an admin
data.access             -- Patient-level data accessed
data.modification       -- Patient/entity data mutated
security.token_rejected -- JWT rejected (v1.0 issuer, bad sig, expired)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

_audit_logger = logging.getLogger("security.audit")


def _emit(event_type: str, **fields: Any) -> None:
    """Write one JSON audit record at WARNING level."""
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event_type,
    }
    record.update(fields)
    _audit_logger.warning(json.dumps(record, default=str))


# ---------------------------------------------------------------------------
# Authentication events
# ---------------------------------------------------------------------------


def emit_login_success(*, email: str, ip: str, session_id_prefix: str) -> None:
    _emit(
        "auth.login.success",
        email=email,
        ip=ip,
        session_prefix=session_id_prefix[:8],
    )


def emit_login_failure(*, reason: str, ip: str, detail: str = "") -> None:
    _emit("auth.login.failure", reason=reason, ip=ip, detail=detail)


def emit_login_mfa_blocked(*, email: str, ip: str, amr: list) -> None:
    _emit("auth.login.mfa_blocked", email=email, ip=ip, amr=amr)


def emit_logout(*, email: str, ip: str) -> None:
    _emit("auth.logout", email=email, ip=ip)


def emit_session_expired(*, ip: str) -> None:
    _emit("auth.session.expired", ip=ip)


def emit_token_rejected(*, reason: str, ip: str) -> None:
    _emit("security.token_rejected", reason=reason, ip=ip)


# ---------------------------------------------------------------------------
# Entra-group resolution (DI-D9D4BA02 / DI-3610585D / R-A4473229)
# ---------------------------------------------------------------------------


def emit_entra_groups_resolved(
    *,
    email: str,
    ip: str,
    group_ids: list[str],
    role_names: list[str],
) -> None:
    """One log line per successful sign-in showing the group->role mapping
    that was applied. Used to evidence access decisions in audit review.
    """
    _emit(
        "auth.entra_groups.resolved",
        email=email,
        ip=ip,
        group_id_count=len(group_ids),
        group_ids=group_ids,
        role_names=role_names,
    )


def emit_groups_claim_missing(*, email: str, ip: str) -> None:
    """The verified token contained no `groups` claim and no overage
    indicator. The tenant administrator likely needs to set
    ``groupMembershipClaims=SecurityGroup`` on the LEO app registration.
    """
    _emit("auth.entra_groups.missing", email=email, ip=ip)


def emit_groups_claim_overage(*, email: str, ip: str) -> None:
    """The token presented `_claim_names.groups`, indicating the user is in
    more groups than Entra will inline. LEO refuses to call Microsoft Graph
    (per DI-3610585D) and falls back to existing HAS_ROLE edges.
    """
    _emit("auth.entra_groups.overage", email=email, ip=ip)


def emit_unknown_entra_group(*, email: str, ip: str, group_id: str) -> None:
    """A group object ID in the user's claim has no `:Group` row in the
    Neo4j catalogue. Either the catalogue is stale or the user is in a
    tenant group that has not been bound to a LEO role.
    """
    _emit(
        "auth.entra_groups.unknown_group",
        email=email,
        ip=ip,
        group_id=group_id,
    )


# ---------------------------------------------------------------------------
# Authorisation events
# ---------------------------------------------------------------------------


def emit_authz_denied(*, email: str, ip: str, route: str, reason: str) -> None:
    _emit("authz.denied", email=email, ip=ip, route=route, reason=reason)


def emit_admin_action(
    *,
    email: str,
    ip: str,
    action: str,
    resource: str,
    detail: str = "",
) -> None:
    _emit(
        "authz.admin_action",
        email=email,
        ip=ip,
        action=action,
        resource=resource,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Data access / modification events
# ---------------------------------------------------------------------------


def emit_data_access(
    *, email: str, ip: str, resource: str, patient_id_hash: str = ""
) -> None:
    _emit(
        "data.access",
        email=email,
        ip=ip,
        resource=resource,
        patient_id_hash=patient_id_hash,
    )


def emit_data_modification(
    *,
    email: str,
    ip: str,
    action: str,
    resource: str,
    patient_id_hash: str = "",
) -> None:
    _emit(
        "data.modification",
        email=email,
        ip=ip,
        action=action,
        resource=resource,
        patient_id_hash=patient_id_hash,
    )
