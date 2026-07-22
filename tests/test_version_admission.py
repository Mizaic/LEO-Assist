"""Tests for controlled workflow version admission (M2.7)."""

from __future__ import annotations

from libs.workflow.version_admission import (
    VersionRollout,
    parse_version_rollout,
    select_admission_version,
)


def _body(*, tenant_id: str = "org-default", patient_id: str = "p-1") -> dict:
    return {
        "tenant_id": tenant_id,
        "patient_id": patient_id,
        "plan_definition_id": "pd-referral-assessment",
    }


def test_explicit_policy_version_wins() -> None:
    version, reason = select_admission_version(
        {**_body(), "policy_version": "v9"},
        VersionRollout(canary_version="v2", canary_org_allowlist=("org-canary",)),
    )
    assert version == "v9"
    assert reason == "explicit_request"


def test_org_allowlist_selects_canary_version() -> None:
    rollout = VersionRollout(
        default_version="v1",
        canary_version="v2",
        canary_org_allowlist=("org-canary",),
    )
    version, reason = select_admission_version(_body(tenant_id="org-canary"), rollout)
    assert version == "v2"
    assert reason == "org_allowlist"


def test_default_and_canary_versions_admit_side_by_side() -> None:
    rollout = VersionRollout(
        default_version="v1",
        canary_version="v2",
        canary_org_allowlist=("org-canary",),
    )
    default_version, default_reason = select_admission_version(
        _body(tenant_id="org-default"), rollout
    )
    canary_version, canary_reason = select_admission_version(
        _body(tenant_id="org-canary"), rollout
    )
    assert default_version == "v1"
    assert default_reason == "default"
    assert canary_version == "v2"
    assert canary_reason == "org_allowlist"


def test_deterministic_allocation_is_stable() -> None:
    rollout = VersionRollout(
        default_version="v1",
        canary_version="v2",
        canary_percent=50,
    )
    body = _body(tenant_id="org-split")
    first = select_admission_version(body, rollout, admission_key="admit-key-1")
    second = select_admission_version(body, rollout, admission_key="admit-key-1")
    assert first == second


def test_rollback_changes_default_for_new_runs_only() -> None:
    rollout = VersionRollout(
        default_version="v3",
        canary_version="v3",
        rollback_target="v2",
    )
    version, reason = select_admission_version(_body(), rollout)
    assert version == "v2"
    assert reason == "rollback_default"


def test_parse_version_rollout_reads_snake_and_camel_case() -> None:
    rollout = parse_version_rollout(
        {
            "_versionRollout": {
                "defaultVersion": "v1",
                "canaryVersion": "v2",
                "canaryOrgAllowlist": ["org-a"],
                "canaryPercent": 10,
                "rollbackTarget": "v1",
            }
        }
    )
    assert rollout.default_version == "v1"
    assert rollout.canary_version == "v2"
    assert rollout.canary_org_allowlist == ("org-a",)
    assert rollout.canary_percent == 10
