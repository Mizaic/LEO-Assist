"""Verification tests for the idempotent role + Entra-binding seeder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libs.cypher.entra_group_queries import (
    ENTRA_GROUP_OBJECT_ID_CONSTRAINT,
    LIST_ENTRA_GROUP_BINDINGS,
    SEED_GROUP_BINDINGS,
    SEED_ROLE_PERMISSIONS,
)
from libs.cypher.role_queries import SEED_CANONICAL_ROLES
from scripts import seed_roles_and_groups

EXAMPLE_YAML = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "identity"
    / "entra-group-bindings.example.yaml"
)


def _client_returning(by_query: dict[str, list[dict]]) -> MagicMock:
    client = MagicMock()

    def _run(query: str, **kwargs):
        return list(by_query.get(query, []))

    client.run.side_effect = _run
    return client


def test_seed_runs_constraint_then_roles_then_bindings():
    expected_catalogue = [
        {
            "entra_object_id": "00000000-0000-0000-0000-000000000099",
            "name": "LEO Platform Administrators",
            "role_name": "platform_admin",
            "grant_org_id": "",
        }
    ]
    client = _client_returning(
        {
            SEED_CANONICAL_ROLES: [
                {"name": "triage_clinician"},
                {"name": "clinical_administrator"},
                {"name": "auditor"},
                {"name": "platform_admin"},
            ],
            SEED_GROUP_BINDINGS: expected_catalogue,
            LIST_ENTRA_GROUP_BINDINGS: expected_catalogue,
        }
    )

    result = seed_roles_and_groups.seed(
        bindings_path=EXAMPLE_YAML, client=client
    )

    queries = [c.args[0] for c in client.run.call_args_list]
    assert queries[0] == ENTRA_GROUP_OBJECT_ID_CONSTRAINT
    assert SEED_CANONICAL_ROLES in queries
    assert SEED_ROLE_PERMISSIONS in queries
    assert SEED_GROUP_BINDINGS in queries
    assert queries[-1] == LIST_ENTRA_GROUP_BINDINGS

    assert result["bindings_seeded"] >= 1
    assert "platform_admin" in result["canonical_roles"]
    assert result["catalogue"] == expected_catalogue


def test_non_canonical_role_in_yaml_is_rejected(tmp_path: Path):
    bad = tmp_path / "bindings.yaml"
    bad.write_text(
        "roles: []\n"
        "bindings:\n"
        "  - entra_object_id: g-1\n"
        "    name: Bad\n"
        "    role_name: super_root\n",
        encoding="utf-8",
    )
    client = _client_returning({})
    with pytest.raises(ValueError, match="not canonical"):
        seed_roles_and_groups.seed(bindings_path=bad, client=client)


def test_duplicate_entra_object_id_is_rejected(tmp_path: Path):
    bad = tmp_path / "bindings.yaml"
    bad.write_text(
        "roles: []\n"
        "bindings:\n"
        "  - entra_object_id: g-1\n"
        "    role_name: triage_clinician\n"
        "  - entra_object_id: g-1\n"
        "    role_name: clinical_coder\n",
        encoding="utf-8",
    )
    client = _client_returning({})
    with pytest.raises(ValueError, match="duplicate"):
        seed_roles_and_groups.seed(bindings_path=bad, client=client)


def test_missing_entra_object_id_is_rejected(tmp_path: Path):
    bad = tmp_path / "bindings.yaml"
    bad.write_text(
        "roles: []\n"
        "bindings:\n"
        "  - role_name: triage_clinician\n",
        encoding="utf-8",
    )
    client = _client_returning({})
    with pytest.raises(ValueError, match="missing entra_object_id"):
        seed_roles_and_groups.seed(bindings_path=bad, client=client)


def test_missing_yaml_path_raises(tmp_path: Path):
    client = _client_returning({})
    with pytest.raises(FileNotFoundError):
        seed_roles_and_groups.seed(
            bindings_path=tmp_path / "does-not-exist.yaml", client=client
        )
