"""Verification tests for the Entra-group -> LEO role resolution + sync flow.

VT-67FB9C97 acceptance criteria, exercised against a mocked PatientGraphClient:

1. AC-1  Token with no `groups` claim emits `auth.entra_groups.missing` and
         returns ``GroupSyncResult.empty_fallthrough()`` -- no edges touched.
2. AC-2  Token with `_claim_names.groups` (overage) emits
         `auth.entra_groups.overage` and falls through.
3. AC-3  A single known group ID is resolved to its canonical role and the
         user ends up as a member of that Entra group.
4. AC-4  Multiple groups deduplicate to a sorted role-name list.
5. AC-5  An unknown group ID emits `auth.entra_groups.unknown_group` per ID
         and is dropped from the final role-name list.
6. AC-6  A non-canonical role coming back from the catalogue is dropped at
         runtime by the canonical-role filter.
7. AC-7  The membership sync issues DROP_STALE_IS_MEMBER_OF on every call so
         removed Entra group memberships drop their edge.
8. AC-8  An empty group_ids list (claim present but empty) is treated as
         missing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.auth import entra_group_sync
from libs.auth.entra_group_sync import (
    GroupSyncResult,
    resolve_and_sync_entra_groups,
)
from libs.cypher.entra_group_queries import (
    ADD_IS_MEMBER_OF,
    DROP_STALE_IS_MEMBER_OF,
    RESOLVE_ROLES_FROM_ENTRA_GROUPS,
)


def _make_client(resolve_rows: list[dict[str, Any]] | None = None) -> MagicMock:
    """Return a MagicMock PatientGraphClient that returns ``resolve_rows`` for
    the RESOLVE_ROLES_FROM_ENTRA_GROUPS query and [] for everything else."""
    client = MagicMock()

    def _run(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        if query == RESOLVE_ROLES_FROM_ENTRA_GROUPS:
            return list(resolve_rows or [])
        return []

    client.run.side_effect = _run
    return client


def _queries_run(client: MagicMock) -> list[str]:
    return [call.args[0] for call in client.run.call_args_list]


def _kwargs_for(client: MagicMock, query: str) -> list[dict[str, Any]]:
    return [call.kwargs for call in client.run.call_args_list if call.args[0] == query]


def test_missing_groups_claim_audits_and_falls_through():
    client = _make_client()
    with (
        patch.object(entra_group_sync, "emit_groups_claim_missing") as mock_missing,
        patch.object(entra_group_sync, "emit_groups_claim_overage") as mock_overage,
        patch.object(entra_group_sync, "emit_unknown_entra_group") as mock_unknown,
    ):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"sub": "abc"},
            ip="10.0.0.1",
            client=client,
        )

    assert result == GroupSyncResult.empty_fallthrough()
    mock_missing.assert_called_once_with(email="user@example.com", ip="10.0.0.1")
    mock_overage.assert_not_called()
    mock_unknown.assert_not_called()
    assert client.run.call_count == 0  # no Neo4j writes on fall-through


def test_overage_claim_audits_and_falls_through():
    client = _make_client()
    with (
        patch.object(entra_group_sync, "emit_groups_claim_overage") as mock_overage,
        patch.object(entra_group_sync, "emit_groups_claim_missing") as mock_missing,
    ):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"_claim_names": {"groups": "src1"}},
            ip="10.0.0.2",
            client=client,
        )

    assert result.fallthrough is True
    assert result.role_names == []
    mock_overage.assert_called_once_with(email="user@example.com", ip="10.0.0.2")
    mock_missing.assert_not_called()
    assert client.run.call_count == 0


def test_empty_groups_list_is_treated_as_missing():
    client = _make_client()
    with patch.object(entra_group_sync, "emit_groups_claim_missing") as mock_missing:
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": []},
            ip="10.0.0.3",
            client=client,
        )

    assert result.fallthrough is True
    mock_missing.assert_called_once()


def test_single_known_group_resolves_to_one_role_and_writes_edges():
    rows = [{"entra_object_id": "G-1", "role_name": "triage_clinician"}]
    client = _make_client(resolve_rows=rows)

    with (
        patch.object(entra_group_sync, "emit_entra_groups_resolved") as mock_resolved,
        patch.object(entra_group_sync, "emit_unknown_entra_group") as mock_unknown,
    ):
        result = resolve_and_sync_entra_groups(
            email="USER@example.com",
            id_claims={"groups": ["G-1"]},
            ip="10.0.0.4",
            client=client,
        )

    assert result.role_names == ["triage_clinician"]
    assert result.unknown_group_ids == []
    assert result.fallthrough is False

    queries = _queries_run(client)
    assert RESOLVE_ROLES_FROM_ENTRA_GROUPS in queries
    assert DROP_STALE_IS_MEMBER_OF in queries
    assert ADD_IS_MEMBER_OF in queries

    drop_kwargs = _kwargs_for(client, DROP_STALE_IS_MEMBER_OF)[0]
    add_kwargs = _kwargs_for(client, ADD_IS_MEMBER_OF)[0]
    assert drop_kwargs["email"] == "user@example.com"
    assert drop_kwargs["group_object_ids"] == ["G-1"]
    assert add_kwargs["email"] == "user@example.com"
    assert add_kwargs["group_object_ids"] == ["G-1"]

    mock_resolved.assert_called_once_with(
        email="user@example.com",
        ip="10.0.0.4",
        group_ids=["G-1"],
        role_names=["triage_clinician"],
    )
    mock_unknown.assert_not_called()


def test_multiple_groups_dedupe_and_sort():
    rows = [
        {"entra_object_id": "G-1", "role_name": "triage_clinician"},
        {"entra_object_id": "G-2", "role_name": "triage_clinician"},  # dup role
        {"entra_object_id": "G-3", "role_name": "organization_administrator"},
    ]
    client = _make_client(resolve_rows=rows)

    with patch.object(entra_group_sync, "emit_entra_groups_resolved"):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": ["G-1", "G-2", "G-3"]},
            ip="10.0.0.5",
            client=client,
        )

    assert result.role_names == ["organization_administrator", "triage_clinician"]
    assert result.unknown_group_ids == []


def test_unknown_group_is_audited_and_dropped():
    rows = [{"entra_object_id": "G-KNOWN", "role_name": "triage_clinician"}]
    client = _make_client(resolve_rows=rows)

    with (
        patch.object(entra_group_sync, "emit_unknown_entra_group") as mock_unknown,
        patch.object(entra_group_sync, "emit_entra_groups_resolved") as mock_resolved,
    ):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": ["G-KNOWN", "G-UNKNOWN"]},
            ip="10.0.0.6",
            client=client,
        )

    assert result.role_names == ["triage_clinician"]
    assert result.unknown_group_ids == ["G-UNKNOWN"]

    mock_unknown.assert_called_once_with(
        email="user@example.com",
        ip="10.0.0.6",
        group_id="G-UNKNOWN",
    )
    mock_resolved.assert_called_once()


def test_non_canonical_role_from_catalogue_is_dropped():
    rows = [
        {"entra_object_id": "G-1", "role_name": "triage_clinician"},
        {"entra_object_id": "G-2", "role_name": "ghost_role"},  # not canonical
    ]
    client = _make_client(resolve_rows=rows)

    with patch.object(entra_group_sync, "emit_entra_groups_resolved"):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": ["G-1", "G-2"]},
            ip="10.0.0.7",
            client=client,
        )

    assert result.role_names == ["triage_clinician"]


def test_drop_stale_runs_even_when_no_roles_resolved():
    """If a user is removed from every known Entra group, stale memberships drop."""
    client = _make_client(resolve_rows=[])  # no matches at all

    with (
        patch.object(entra_group_sync, "emit_unknown_entra_group"),
        patch.object(entra_group_sync, "emit_entra_groups_resolved"),
    ):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": ["G-STALE"]},
            ip="10.0.0.8",
            client=client,
        )

    assert result.role_names == []
    assert result.unknown_group_ids == ["G-STALE"]

    drop_calls = _kwargs_for(client, DROP_STALE_IS_MEMBER_OF)
    add_calls = _kwargs_for(client, ADD_IS_MEMBER_OF)
    assert len(drop_calls) == 1
    assert drop_calls[0]["group_object_ids"] == []
    assert add_calls == []


def test_string_groups_claim_is_coerced_to_list():
    rows = [{"entra_object_id": "G-1", "role_name": "clinician_admin"}]
    client = _make_client(resolve_rows=rows)

    with patch.object(entra_group_sync, "emit_entra_groups_resolved"):
        result = resolve_and_sync_entra_groups(
            email="user@example.com",
            id_claims={"groups": "G-1"},
            ip="10.0.0.9",
            client=client,
        )

    assert result.role_names == ["clinician_admin"]


def test_email_normalisation_is_applied_to_neo4j_calls():
    rows = [{"entra_object_id": "G-1", "role_name": "administrator"}]
    client = _make_client(resolve_rows=rows)

    with patch.object(entra_group_sync, "emit_entra_groups_resolved"):
        resolve_and_sync_entra_groups(
            email="  Mixed.Case@Example.COM  ",
            id_claims={"groups": ["G-1"]},
            ip="10.0.0.10",
            client=client,
        )

    drop_kwargs = _kwargs_for(client, DROP_STALE_IS_MEMBER_OF)[0]
    assert drop_kwargs["email"] == "mixed.case@example.com"


def test_blank_email_returns_fallthrough():
    client = _make_client()
    result = resolve_and_sync_entra_groups(
        email="   ",
        id_claims={"groups": ["G-1"]},
        ip="10.0.0.11",
        client=client,
    )
    assert result == GroupSyncResult.empty_fallthrough()
    assert client.run.call_count == 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, []),
        ("", []),
        ([], []),
        (["a", " b ", "", None, 1], ["a", "b"]),
        ("solo", ["solo"]),
        (("x", "y"), ["x", "y"]),
        ({"only-iter"}, ["only-iter"]),
        (123, []),
    ],
)
def test_coerce_group_ids(raw, expected):
    assert entra_group_sync._coerce_group_ids(raw) == expected
