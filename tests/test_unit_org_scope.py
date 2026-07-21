"""Unit tests for Service Provider org scope (RBAC multi-tenant).

Atlas: DI-A / DI-B / DI-C SP access; VT-A SP scope unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from libs.auth.org_scope import (
    ORG_PATIENT_FILTER,
    CallerScope,
    _expand_service_provider_scope,
    require_patient_in_scope,
    resolve_caller_scope,
)


@pytest.fixture(autouse=True)
def _no_scope_cache():
    with (
        patch("libs.auth.org_scope._cache_get", return_value=None),
        patch("libs.auth.org_scope._cache_put"),
    ):
        yield


def test_org_patient_filter_contains_gp_registered_and_sp_arms() -> None:
    assert "HAS_GENERAL_PRACTITIONER" in ORG_PATIENT_FILTER
    assert "REGISTERED_IN" in ORG_PATIENT_FILTER
    assert "ReferralRequest" in ORG_PATIENT_FILTER
    assert "PROVIDES_SERVICE" in ORG_PATIENT_FILTER
    assert "PROVIDES_SERVICE_FOR" not in ORG_PATIENT_FILTER
    assert ORG_PATIENT_FILTER.count("EXISTS") >= 3


def test_expand_service_provider_scope_returns_own_id_only() -> None:
    client = MagicMock()
    assert _expand_service_provider_scope(client, "M0L1I") == ["M0L1I"]
    client.run.assert_not_called()


def test_resolve_caller_scope_service_provider() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"email": "ben@nhs.net", "is_platform_admin": False}],
        [
            {
                "id": "M0L1I",
                "nodeLabels": ["ServiceProvider", "Organization"],
            }
        ],
    ]
    scope = resolve_caller_scope(client, "Ben@NHS.NET")
    assert scope.scope_type == "service_provider"
    assert scope.org_ids == ["M0L1I"]
    assert scope.primary_org_id == "M0L1I"
    assert scope.is_admin is False


def test_resolve_caller_scope_gp_regression() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"email": "gp@nhs.net", "is_platform_admin": False}],
        [{"id": "D83007", "nodeLabels": ["GPPractice", "Organization"]}],
        [
            {
                "gp_id": "D83007",
                "pcn_id": None,
                "icb_id": None,
                "ca_id": None,
            }
        ],
    ]
    scope = resolve_caller_scope(client, "gp@nhs.net")
    assert scope.scope_type == "gp"
    assert "D83007" in scope.org_ids


def test_require_patient_in_scope_sp_no_referral_raises_404() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"gp_id": "OTHER_GP"}],
        [{"sp_id": None}],
        [{"sp_id": None}],
    ]
    scope = CallerScope(
        email="sp@nhs.net",
        is_admin=False,
        org_ids=["M0L1I"],
        scope_type="service_provider",
        primary_org_id="M0L1I",
    )
    with pytest.raises(HTTPException) as exc:
        require_patient_in_scope(client, scope, "patient-1")
    assert exc.value.status_code == 404


def test_require_patient_in_scope_sp_via_for_service_passes() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"gp_id": "OTHER_GP"}],
        [{"sp_id": None}],
        [{"sp_id": "M0L1I"}],
    ]
    scope = CallerScope(
        email="sp@nhs.net",
        is_admin=False,
        org_ids=["M0L1I"],
        scope_type="service_provider",
        primary_org_id="M0L1I",
    )
    require_patient_in_scope(client, scope, "patient-1")


def test_require_patient_in_scope_sp_via_workflow_passes() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"gp_id": None}],
        [{"sp_id": "M0L1I"}],
    ]
    scope = CallerScope(
        email="sp@nhs.net",
        is_admin=False,
        org_ids=["M0L1I"],
        scope_type="service_provider",
        primary_org_id="M0L1I",
    )
    require_patient_in_scope(client, scope, "patient-1")
