"""G6.1 rollback drill -- local simulated evidence for Gate 6 release checklist.

Exercises the three rollback mechanisms documented in
compliance/GATE6-RELEASE-CHECKLIST.md section 2:

1. Plan-level version rollback via ``_versionRollout.rollbackTarget``.
2. Emergency kill switch ``DURABLE_ENGINE_DISABLED=true``.
3. Legacy sync engine path for non-durable plans.

Staging DevOps steps (deploy canary, FHIR PlanDefinition PATCH, image rollback)
require live credentials; this module proves control behaviour offline.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    is_durable_runner_enabled,
)
from libs.workflow.plan_manifest import PlanManifest, load_manifest_for_run
from libs.workflow.version_admission import VersionRollout, select_admission_version
from services.pipeline_worker.app.services.durable_dispatcher import is_durable_message


def _body(*, tenant_id: str = "org-staging") -> dict:
    return {
        "tenant_id": tenant_id,
        "patient_id": "p-drill-1",
        "plan_definition_id": "pd-referral-assessment",
    }


def _manifest_v3() -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=3,
        version_node_id="ver-drill-v3",
        policy_version="v3",
        workflow_mode="durable_pubsub",
        actions=(),
    )


def _manifest_v2() -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=2,
        version_node_id="ver-drill-v2",
        policy_version="v2",
        workflow_mode="durable_pubsub",
        actions=(),
    )


def _pinned_row(manifest: PlanManifest) -> dict:
    return {
        "plan_id": manifest.plan_id,
        "version_node_id": manifest.version_node_id,
        "version_id": manifest.version_id,
        "raw_json": json.dumps({"id": manifest.plan_id}),
        "workflow_mode": manifest.workflow_mode,
    }


def test_g6_1_step4_new_run_uses_rollback_version() -> None:
    """After rollbackTarget is set, new admissions select the rollback version."""
    rollout_before = VersionRollout(default_version="v3", canary_version="v3")
    version_before, reason_before = select_admission_version(_body(), rollout_before)
    assert version_before == "v3"
    assert reason_before == "default"

    rollout_after = VersionRollout(
        default_version="v3",
        canary_version="v3",
        rollback_target="v2",
    )
    version_after, reason_after = select_admission_version(_body(), rollout_after)
    assert version_after == "v2"
    assert reason_after == "rollback_default"


def test_g6_1_step5_inflight_run_keeps_pinned_manifest() -> None:
    """In-flight run keeps v3 manifest even after rollbackTarget moves new runs to v2."""
    inflight_run_id = "run-g6-inflight-v3"
    mock_pg = MagicMock()
    mock_pg.run.return_value = [_pinned_row(_manifest_v3())]
    mock_pg.close = MagicMock()

    pinned = load_manifest_for_run(
        inflight_run_id,
        "pd-referral-assessment",
        "v2",
        client=mock_pg,
    )
    assert pinned.policy_version == "v3"
    assert pinned.version_node_id == "ver-drill-v3"

    rollout_after = VersionRollout(
        default_version="v3",
        rollback_target="v2",
    )
    new_version, new_reason = select_admission_version(_body(), rollout_after)
    assert new_version == "v2"
    assert new_reason == "rollback_default"

    mock_pg.run.return_value = [_pinned_row(_manifest_v2())]
    new_run = load_manifest_for_run(
        "run-g6-new-v2",
        "pd-referral-assessment",
        "v2",
        client=mock_pg,
    )
    assert new_run.policy_version == "v2"
    assert new_run.version_node_id == "ver-drill-v2"


def test_g6_1_kill_switch_blocks_new_triggers_not_inflight_steps(monkeypatch) -> None:
    """DURABLE_ENGINE_DISABLED blocks new durable triggers but not in-flight steps."""
    monkeypatch.setenv("DURABLE_ENGINE_DISABLED", "true")

    inflight = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-g6-inflight",
    }
    new_trigger = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-g6-blocked",
    }

    assert is_durable_runner_enabled("pd-referral-assessment") is False
    assert is_durable_message(inflight) is True
    assert is_durable_message(new_trigger) is False


def test_g6_1_legacy_plan_stays_off_durable_path(monkeypatch) -> None:
    """Non-durable plans are not routed through DurableStepRunner triggers."""
    monkeypatch.delenv("DURABLE_ENGINE_DISABLED", raising=False)

    legacy_plan_id = "pd-legacy-in-process-not-seeded"
    legacy_trigger = {
        "event_type": "gold-audit-request",
        "plan_definition_id": legacy_plan_id,
        "run_id": "run-g6-legacy",
    }
    assert is_durable_runner_enabled(legacy_plan_id) is False
    assert is_durable_message(legacy_trigger) is False


@pytest.mark.parametrize(
    "plan_id,expected_mode",
    [
        ("pd-referral-assessment", "durable_pubsub"),
        ("pd-gp-encounter-coding", "durable_pubsub"),
    ],
)
def test_g6_1_seed_plans_declare_durable_pubsub(
    plan_id: str, expected_mode: str
) -> None:
    """Seed definitions pin durable_pubsub on migrated reference plans."""
    from libs.workflow.plan_manifest import resolve_plan_workflow_mode

    assert resolve_plan_workflow_mode(plan_id) == expected_mode
