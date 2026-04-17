"""Verification tests for Wave D role-first auth additions.

Covers VT-LEO-AI-125:
  TC-001 session payload carries selected_role and allowed_roles
  TC-002 role switch updates Practitioner and writes (:RoleSwitch) audit
  TC-003 unauthorised role is rejected with 403
  TC-004 canonical roles seed is idempotent

The Neo4j layer is mocked via libs.neo4j_client.client.PatientGraphClient
so the tests run without a live graph. See DI-LEO-AI-129.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.auth.role_state import (
    RoleNotAllowedError,
    RoleState,
    fetch_role_state,
    set_selected_role,
)
from scripts import seed_canonical_roles as seed_script


# -----------------------------------------------------------------------------
# VT-125-TC-001  -- session payload carries role fields
# -----------------------------------------------------------------------------
@patch("libs.auth.role_state.PatientGraphClient")
def test_fetch_role_state_returns_selected_and_allowed(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [
        {
            "selected_role": "clinician",
            "allowed_roles": ["clinician", "staff"],
        }
    ]
    state = fetch_role_state("Rob@Test.AI ")
    assert state.selected_role == "clinician"
    assert state.allowed_roles == ["clinician", "staff"]


@patch("libs.auth.role_state.PatientGraphClient")
def test_fetch_role_state_drops_unknown_roles(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [
        {
            "selected_role": "admin_v2",
            "allowed_roles": ["staff", "admin_v2", None],
        }
    ]
    state = fetch_role_state("user@x.com")
    assert state.selected_role is None
    assert state.allowed_roles == ["staff"]


@patch("libs.auth.role_state.PatientGraphClient")
def test_fetch_role_state_missing_practitioner_is_empty(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = []
    state = fetch_role_state("nobody@x.com")
    assert state == RoleState(selected_role=None, allowed_roles=[])


# -----------------------------------------------------------------------------
# VT-125-TC-002  -- role switch updates Practitioner and writes audit
# -----------------------------------------------------------------------------
@patch("libs.auth.role_state.PatientGraphClient")
def test_set_selected_role_writes_audit_and_updates(
    MockClient: MagicMock,
) -> None:
    # Two client instances are created: one in fetch_role_state (for the
    # current state) and one in set_selected_role (for audit + set).
    pre_instance = MagicMock()
    pre_instance.run.return_value = [
        {
            "selected_role": "clinician",
            "allowed_roles": ["clinician", "staff"],
        }
    ]
    post_instance = MagicMock()
    post_instance.run.side_effect = [
        [{"id": "audit-1"}],
        [
            {
                "selected_role": "staff",
                "allowed_roles": ["clinician", "staff"],
            }
        ],
    ]
    MockClient.side_effect = [pre_instance, post_instance]

    updated = set_selected_role("rob@test.ai", "staff", "sess-1")

    assert updated.selected_role == "staff"
    assert updated.allowed_roles == ["clinician", "staff"]
    # Audit write and set-role write are the two calls on the post_instance.
    assert post_instance.run.call_count == 2
    first_call = post_instance.run.call_args_list[0]
    assert first_call.kwargs.get("to_role") == "staff"
    assert first_call.kwargs.get("from_role") == "clinician"
    assert first_call.kwargs.get("session_id") == "sess-1"


# -----------------------------------------------------------------------------
# VT-125-TC-003  -- unauthorised role is rejected with 403 (at service layer,
# manifested as RoleNotAllowedError which the router translates to 403).
# -----------------------------------------------------------------------------
@patch("libs.auth.role_state.PatientGraphClient")
def test_set_selected_role_rejects_role_not_allowed(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [
        {"selected_role": "clinician", "allowed_roles": ["clinician"]}
    ]
    with pytest.raises(RoleNotAllowedError):
        set_selected_role("rob@test.ai", "platform_admin", "sess-1")


# -----------------------------------------------------------------------------
# VT-125-TC-004  -- canonical roles seed is idempotent
# -----------------------------------------------------------------------------
def test_seed_canonical_roles_merges_all_four() -> None:
    client = MagicMock()
    client.run.return_value = [
        {"name": "clinician"},
        {"name": "staff"},
        {"name": "qa_ra_lead"},
        {"name": "platform_admin"},
    ]
    names = seed_script.seed(client=client)
    assert set(names) == {"clinician", "staff", "qa_ra_lead", "platform_admin"}
    client.run.assert_called_once()
    args, kwargs = client.run.call_args
    assert kwargs.get("role_names") == [
        "clinician",
        "staff",
        "qa_ra_lead",
        "platform_admin",
    ]


def test_seed_canonical_roles_uses_merge_clause() -> None:
    # Inspect the query string to confirm MERGE (idempotent) rather than
    # CREATE. This is a cheap guard against an accidental regression.
    from libs.cypher.role_queries import SEED_CANONICAL_ROLES

    assert "MERGE (r:Role" in SEED_CANONICAL_ROLES
    assert "ON CREATE SET" in SEED_CANONICAL_ROLES
