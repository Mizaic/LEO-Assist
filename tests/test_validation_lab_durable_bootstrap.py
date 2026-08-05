"""Validation Lab eager durable bootstrap (DI-2289D095)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.validation_lab import service as lab_service
from libs.validation_lab.models import PersistMode, ValidationCaseSpec
from libs.validation_lab.pipeline import bootstrap_durable_lab_run
from tests.test_validation_lab import FakeClient, _fake_materialise


class _FakeBus:
    async def close(self) -> None:
        return None


def test_bootstrap_skips_non_lab_source(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[dict[str, Any]] = []

    async def _fake_start(body: dict[str, Any], *, bus: Any, queue_name: str) -> None:
        called.append(body)

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.is_durable_runner_enabled",
        lambda plan_id: True,
    )
    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
    )
    err = bootstrap_durable_lab_run(
        {
            "plan_definition_id": "pd-referral-assessment",
            "context": {"source": "production"},
        }
    )
    assert err is None
    assert called == []


def test_bootstrap_calls_durable_start_for_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[dict[str, Any]] = []

    async def _fake_start(body: dict[str, Any], *, bus: Any, queue_name: str) -> None:
        called.append(body)

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.is_durable_runner_enabled",
        lambda plan_id: plan_id == "pd-referral-assessment",
    )
    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _FakeBus(),
    )
    body = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "lab-run-1",
        "context": {"source": "validation-lab", "case_id": "case-1"},
    }
    err = bootstrap_durable_lab_run(body)
    assert err is None
    assert called == [body]


def test_start_run_marks_running_after_eager_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p-boot"))
    monkeypatch.setattr(
        lab_service, "resolve_ruleset_version", lambda explicit=None: None
    )
    lab_service.create_case(
        client,
        ValidationCaseSpec(
            case_id="case-boot", title="t", referral_text="Referral body text."
        ),
    )

    async def _fake_start(body: dict[str, Any], *, bus: Any, queue_name: str) -> None:
        client.pipeline_runs[body["run_id"]] = {
            "status": "running",
            "assessment_id": "",
        }

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
    )
    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _FakeBus(),
    )

    packed = lab_service.start_run(
        client,
        case_id="case-boot",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction", "sbar"],
        persist_mode=PersistMode.production,
        publish=lambda body, run_id: None,
        eager_durable_bootstrap=True,
    )
    assert packed["run"]["status"] == "running"
