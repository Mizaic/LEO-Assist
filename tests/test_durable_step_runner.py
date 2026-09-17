"""Unit tests for libs/workflow/durable_step_runner.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
    _build_outgoing_edges,
    _evaluate_condition_port,
    _resolve_next_action_ids,
    is_durable_runner_enabled,
)
from libs.workflow.durable_steps import StepResult as DurableStepResult
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.pipeline_stage_store import (
    PipelineStageStore,
    StageClaimResult,
    StageCompleteResult,
)
from libs.workflow.pipeline_outbox import build_first_step_message_id


def _manifest(*actions: _Action) -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-test-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=tuple(actions),
    )


# ---------------------------------------------------------------------------
# is_durable_runner_enabled
# ---------------------------------------------------------------------------


def test_kill_switch_blocks_durable_plans(monkeypatch):
    monkeypatch.setenv("DURABLE_ENGINE_DISABLED", "true")
    assert is_durable_runner_enabled("pd-referral-assessment") is False
    assert is_durable_runner_enabled("pd-gp-encounter-coding") is False


def test_durable_pubsub_plans_enabled_by_workflow_mode(monkeypatch):
    monkeypatch.delenv("DURABLE_ENGINE_DISABLED", raising=False)
    assert is_durable_runner_enabled("pd-referral-assessment") is True
    assert is_durable_runner_enabled("pd-gp-encounter-coding") is True
    assert is_durable_runner_enabled("pd-gold-training-audit") is True
    assert is_durable_runner_enabled("pd-episode-bundle-coding") is True


def test_non_durable_plan_stays_on_workflow_engine(monkeypatch):
    monkeypatch.delenv("DURABLE_ENGINE_DISABLED", raising=False)
    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.resolve_plan_workflow_mode",
        lambda plan_id: "" if plan_id == "pd-legacy-in-process" else "durable_pubsub",
    )
    assert is_durable_runner_enabled("pd-legacy-in-process") is False
    assert is_durable_runner_enabled("pd-gp-encounter-coding") is True


# ---------------------------------------------------------------------------
# Plan manifest loading (pinned PlanDefinitionVersion)
# ---------------------------------------------------------------------------


def test_start_pins_policy_version_on_admission():
    trigger_action = _Action(
        action_id="act-trigger",
        subgraph_id="trigger",
        node_type="trigger",
        trigger_name="referral-received",
    )
    manifest = _manifest(trigger_action)
    mock_store = MagicMock(
        ensure_schema=MagicMock(),
        admit_run=MagicMock(
            return_value=MagicMock(
                run_id="run-001",
                created=True,
                first_step_enqueued=False,
                status="running",
            )
        ),
        claim_first_step_enqueue=MagicMock(return_value=True),
    )
    mock_bus = AsyncMock()

    with (
        patch(
            "libs.workflow.durable_step_runner.load_rollout_for_plan",
            return_value=__import__(
                "libs.workflow.version_admission", fromlist=["VersionRollout"]
            ).VersionRollout(default_version="v1"),
        ),
        patch(
            "libs.workflow.durable_step_runner.load_plan_manifest",
            return_value=manifest,
        ),
        patch(
            "libs.workflow.execution_manifest.build_manifest_for_plan",
            return_value={"plan_version_id": "ver-test-1", "policy_version": "v1"},
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=mock_store,
        ),
    ):
        asyncio.run(
            DurableStepRunner.start(
                {
                    "event_type": "referral-received",
                    "plan_definition_id": "pd-referral-assessment",
                    "run_id": "run-001",
                    "patient_id": "p-001",
                },
                bus=mock_bus,
            )
        )

    admit_kwargs = mock_store.admit_run.call_args.kwargs
    assert admit_kwargs["plan_version_id"] == "ver-test-1"
    assert admit_kwargs["policy_version"] == "v1"
    assert admit_kwargs["version_selection_reason"] == "default"
    assert "execution_manifest_json" in admit_kwargs


# ---------------------------------------------------------------------------
# _build_outgoing_edges
# ---------------------------------------------------------------------------


def _make_action(action_id, related_actions=None, related_edges=None):
    return _Action(
        action_id=action_id,
        subgraph_id="extraction",
        related_actions=related_actions or [],
        related_edges=related_edges or [],
    )


def test_build_outgoing_from_related_actions():
    a = _make_action("act-a")
    b = _make_action("act-b", related_actions=[{"actionId": "act-a"}])
    outgoing = _build_outgoing_edges([a, b])
    assert "act-a" in outgoing
    assert outgoing["act-a"][0]["target"] == "act-b"


def test_build_outgoing_deduplicates():
    b = _make_action(
        "act-b",
        related_actions=[{"actionId": "act-a"}],
        related_edges=[{"actionId": "act-a"}],
    )
    outgoing = _build_outgoing_edges([_make_action("act-a"), b])
    assert len(outgoing["act-a"]) == 1


# ---------------------------------------------------------------------------
# _evaluate_condition_port
# ---------------------------------------------------------------------------


def test_condition_matches_rule():
    action = _Action(
        action_id="act-cond",
        subgraph_id="condition",
        node_type="condition",
        config={
            "params": {
                "rules": [
                    {
                        "field": "extraction_failed",
                        "operator": "==",
                        "value": "true",
                        "outputPort": "failed",
                    }
                ],
                "defaultPort": "ok",
            }
        },
    )
    assert _evaluate_condition_port(action, {"extraction_failed": "true"}) == "failed"
    assert _evaluate_condition_port(action, {"extraction_failed": "false"}) == "ok"


# ---------------------------------------------------------------------------
# _resolve_next_action_ids
# ---------------------------------------------------------------------------


def test_resolve_next_plain_action():
    action = _make_action("act-a")
    b = _make_action("act-b", related_actions=[{"actionId": "act-a"}])
    outgoing = _build_outgoing_edges([action, b])
    result = DurableStepResult(status="completed")
    next_ids = _resolve_next_action_ids(action, result, outgoing)
    assert next_ids == ["act-b"]


def test_resolve_next_condition_takes_default():
    cond = _Action(
        action_id="act-cond",
        subgraph_id="condition",
        node_type="condition",
    )
    ok_action = _Action(
        action_id="act-ok",
        subgraph_id="post_processing",
        related_edges=[
            {"actionId": "act-cond", "sourceHandle": "ok", "targetHandle": None}
        ],
    )
    fail_action = _Action(
        action_id="act-fail",
        subgraph_id="notify",
        related_edges=[
            {"actionId": "act-cond", "sourceHandle": "else", "targetHandle": None}
        ],
    )
    outgoing = _build_outgoing_edges([cond, ok_action, fail_action])
    result = DurableStepResult(status="completed", output={"condition_port": "else"})
    next_ids = _resolve_next_action_ids(cond, result, outgoing)
    assert next_ids == ["act-fail"]


# ---------------------------------------------------------------------------
# DurableStepRunner.start (mocked Neo4j + bus)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_publishes_first_action():
    trigger_action = _Action(
        action_id="act-trigger",
        subgraph_id="trigger",
        node_type="trigger",
        trigger_name="referral-received",
    )
    first_action = _Action(
        action_id="act-ref-extract",
        subgraph_id="extraction",
        related_actions=[{"actionId": "act-trigger"}],
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()

    body = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-001",
        "patient_id": "p-001",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_plan_manifest",
            return_value=_manifest(trigger_action, first_action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
                close=MagicMock(),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                admit_run=MagicMock(
                    return_value=MagicMock(
                        run_id="run-001",
                        created=True,
                        first_step_enqueued=False,
                        status="running",
                    )
                ),
                claim_first_step_enqueue=MagicMock(return_value=True),
            ),
        ),
    ):
        await DurableStepRunner.start(body, bus=mock_bus)

    mock_bus.send.assert_called_once()
    sent_message = mock_bus.send.call_args[0][1]
    sent_body = sent_message.body
    assert sent_body["action_id"] == "act-ref-extract"
    assert sent_body["event_type"] == DURABLE_STEP_EVENT
    assert sent_message.message_id == build_first_step_message_id(
        "run-001", "act-ref-extract"
    )


# ---------------------------------------------------------------------------
# DurableStepRunner.run_step (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_step_invokes_subgraph_and_publishes_next():
    current_action = _Action(
        action_id="act-ref-extract",
        subgraph_id="extraction",
    )
    next_action = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"entities": []})

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-002",
        "patient_id": "p-002",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current_action, next_action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                upsert_run=MagicMock(),
                claim_stage=MagicMock(return_value=StageClaimResult(outcome="claimed")),
                complete_stage=MagicMock(),
                load_pending_outbox=MagicMock(return_value=[]),
                has_pending_outbox=MagicMock(return_value=False),
                mark_outbox_sent=MagicMock(),
                mark_next_published=MagicMock(),
            ),
        ) as store_cls,
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=1,
        ) as dispatch_mock,
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-002", "entities": []},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    assert result.next_event_type == DURABLE_STEP_EVENT
    assert result.next_step_id == "act-ref-post-process"
    store = store_cls.return_value
    completed_result = store.complete_stage.call_args[0][1]
    assert completed_result.next_event_type == DURABLE_STEP_EVENT
    dispatch_mock.assert_called_once()
    mock_bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_terminal_publishes_completion():
    terminal_action = _Action(
        action_id="act-ref-sbar",
        subgraph_id="sbar",
        completion_queue="referral-assessments-output",
        completion_event_type="referral_assessment_completed",
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"sbar_assessment_id": "assess-1"})

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-sbar",
        "step_id": "act-ref-sbar",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-003",
        "patient_id": "p-003",
        "context": {"ubrn": "000481914514"},
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(terminal_action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                upsert_run=MagicMock(),
                claim_stage=MagicMock(return_value=StageClaimResult(outcome="claimed")),
                complete_stage=MagicMock(),
                mark_next_published=MagicMock(),
                write_completion_event=MagicMock(),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-003"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    mock_bus.send.assert_called_once()
    sent_body = mock_bus.send.call_args[0][1].body
    assert sent_body == {
        "event_type": "referral_assessment_completed",
        "run_id": "run-003",
        "ubrn": "000481914514",
        "assessment_id": "assess-1",
    }


@pytest.mark.asyncio
async def test_run_step_defers_when_stage_busy():
    action = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    mock_bus = AsyncMock()
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-busy",
        "patient_id": "p-busy",
        "_message_id": "msg-busy",
    }
    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
        ) as store_cls,
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-busy"},
        ),
    ):
        from libs.workflow.stage_lease import StageLeaseBusyError

        mock_store = MagicMock(
            ensure_schema=MagicMock(),
            upsert_run=MagicMock(),
            claim_stage=MagicMock(return_value=StageClaimResult(outcome="busy")),
            complete_stage=MagicMock(),
        )
        store_cls.return_value = mock_store

        with pytest.raises(StageLeaseBusyError):
            await DurableStepRunner.run_step(body, bus=mock_bus)

    mock_store.complete_stage.assert_not_called()
    mock_bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_dual_delivery_executes_subgraph_once():
    """Two deliveries of the same stage run the subgraph exactly once."""
    from tests.helpers.claim_race_client import InMemoryClaimClient

    action = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    nxt = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )
    client = InMemoryClaimClient()
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    executions: list[int] = []
    mock_graph = MagicMock()

    def _invoke(_state):
        executions.append(1)
        return {"entities": []}

    mock_graph.invoke = _invoke
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-dual",
        "patient_id": "p-dual",
    }
    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(action, nxt),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-dual"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        first = await DurableStepRunner.run_step(body, bus=mock_bus)
        second = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert first.status == "completed"
    assert second.status == "completed"
    assert "already_completed" in second.warnings
    assert executions == [1]


@pytest.mark.asyncio
async def test_run_step_stale_complete_recovers_when_stage_already_finished():
    """Duplicate delivery that loses the complete race still finishes cleanly."""
    from tests.helpers.claim_race_client import InMemoryClaimClient

    action = _Action(action_id="act-ref-persist", subgraph_id="persist")
    client = InMemoryClaimClient()
    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"documents_written": 2})
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-persist",
        "step_id": "act-ref-persist",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-persist-stale",
        "patient_id": "p-persist-stale",
        "_message_id": "msg-persist-stale",
    }
    store = PipelineStageStore(client)
    real_complete = store.complete_stage

    def _complete_as_stale(*args, **kwargs):
        real_complete(*args, **kwargs)
        return StageCompleteResult(outcome="stale_lease")

    store.complete_stage = _complete_as_stale  # type: ignore[method-assign]

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-persist-stale"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    assert "already_completed" in result.warnings
    mock_graph.invoke.assert_called_once()


@pytest.mark.asyncio
async def test_run_step_already_completed_republishes_next():
    current = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    nxt = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )
    mock_bus = AsyncMock()
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-done",
        "patient_id": "p-done",
    }
    store = MagicMock(
        ensure_schema=MagicMock(),
        upsert_run=MagicMock(),
        claim_stage=MagicMock(
            return_value=StageClaimResult(
                outcome="already_completed",
                output={"entities": []},
                next_action_ids=["act-ref-post-process"],
                next_published=False,
            )
        ),
        complete_stage=MagicMock(),
        load_pending_outbox=MagicMock(return_value=[]),
        has_pending_outbox=MagicMock(return_value=False),
        mark_outbox_sent=MagicMock(),
        mark_next_published=MagicMock(),
    )
    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current, nxt),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-done"},
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=1,
        ) as dispatch_mock,
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    assert "already_completed" in result.warnings
    store.complete_stage.assert_not_called()
    dispatch_mock.assert_called_once()
    mock_bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_stale_lease_without_recovery_raises_defer():
    """Unrecovered stale complete must raise StageLeaseStaleError for SB abandon."""
    from libs.workflow.stage_lease import StageLeaseStaleError

    action = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"entities": []})
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-stale-defer",
        "patient_id": "p-stale-defer",
        "_message_id": "msg-stale-defer",
    }
    claim = StageClaimResult(
        outcome="claimed",
        lease_owner="worker-a",
        lease_generation=1,
    )
    store = MagicMock(
        ensure_schema=MagicMock(),
        upsert_run=MagicMock(),
        claim_stage=MagicMock(side_effect=[claim, StageClaimResult(outcome="busy")]),
        complete_stage=MagicMock(
            return_value=StageCompleteResult(outcome="stale_lease")
        ),
    )
    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-stale-defer"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        with pytest.raises(StageLeaseStaleError):
            await DurableStepRunner.run_step(body, bus=mock_bus)

    mock_graph.invoke.assert_called_once()


@pytest.mark.asyncio
async def test_run_step_records_llm_usage_in_metrics():
    """LLM tokens from extraction subgraph must appear in metrics_json.

    DI: DI-36F80B95  (durable step runner - extraction token audit)
    """
    from libs.llm_client.token_tracker import track_llm_usage_sync

    current_action = _Action(
        action_id="act-ref-extract",
        subgraph_id="extraction",
    )

    def fake_invoke(state):
        track_llm_usage_sync(
            agent_task="v3_pipeline_extractor",
            model_name="gpt-5-mini",
            model_provider="azure",
            model_tier="small",
            input_tokens=8000,
            output_tokens=600,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            reasoning_tokens=0,
            latency_ms=1200,
            success=True,
            error_message="",
        )
        return {"entities": [{"id": "e1"}]}

    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(side_effect=fake_invoke)

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-llm-usage-001",
        "patient_id": "p-llm-001",
    }

    captured_metrics: dict = {}

    def capture_complete(request, result, **kwargs):
        captured_metrics.update(result.metrics)
        return StageCompleteResult(outcome="committed")

    store_mock = MagicMock(
        ensure_schema=MagicMock(),
        upsert_run=MagicMock(),
        claim_stage=MagicMock(return_value=StageClaimResult(outcome="claimed")),
        complete_stage=MagicMock(side_effect=capture_complete),
        load_pending_outbox=MagicMock(return_value=[]),
        has_pending_outbox=MagicMock(return_value=False),
        mark_outbox_sent=MagicMock(),
        mark_next_published=MagicMock(),
    )

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current_action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store_mock,
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-llm-001", "entities": []},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        await DurableStepRunner.run_step(body, bus=mock_bus)

    assert "llm_usage" in captured_metrics, "llm_usage key missing from stage metrics"
    usage = captured_metrics["llm_usage"]
    assert usage["input_tokens"] == 8000
    assert usage["output_tokens"] == 600
    assert usage["llm_calls"] == 1
    assert usage["cost_usd"] > 0, "cost_usd should be positive for azure/small"


@pytest.mark.asyncio
async def test_nested_sbar_recorder_still_writes_stage_llm_usage():
    """SBAR's own recorder must not blank act-ref-sbar metrics_json.

    DI-9456E5BE -- 16 Sep SBAR stages stored no llm_usage while Azure billed.
    """
    from libs.llm_client.token_tracker import track_llm_usage_sync
    from libs.llm_client.usage_recorder import LLMUsageRecorder

    current_action = _Action(action_id="act-ref-sbar", subgraph_id="sbar")

    def fake_invoke(state):
        with LLMUsageRecorder():
            track_llm_usage_sync(
                agent_task="sbar_background",
                model_name="gpt-5.4-mini",
                model_provider="azure",
                model_tier="small",
                input_tokens=140000,
                output_tokens=1600,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                reasoning_tokens=0,
                latency_ms=8000,
                success=True,
                error_message="",
            )
        return {"sbar_status": "completed"}

    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(side_effect=fake_invoke)
    captured_metrics: dict = {}

    def capture_complete(request, result, **kwargs):
        captured_metrics.update(result.metrics)
        return StageCompleteResult(outcome="completed")

    store_mock = MagicMock(
        ensure_schema=MagicMock(),
        upsert_run=MagicMock(),
        claim_stage=MagicMock(return_value=StageClaimResult(outcome="claimed")),
        complete_stage=MagicMock(side_effect=capture_complete),
        load_pending_outbox=MagicMock(return_value=[]),
        has_pending_outbox=MagicMock(return_value=False),
        mark_outbox_sent=MagicMock(),
        mark_next_published=MagicMock(),
        get_run_status=MagicMock(return_value="completed"),
    )

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current_action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store_mock,
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-sbar-001", "entities": []},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        await DurableStepRunner.run_step(
            {
                "event_type": DURABLE_STEP_EVENT,
                "action_id": "act-ref-sbar",
                "step_id": "act-ref-sbar",
                "plan_definition_id": "pd-referral-assessment",
                "run_id": "run-sbar-nested-001",
                "patient_id": "p-sbar-001",
            },
            bus=mock_bus,
        )

    usage = captured_metrics.get("llm_usage") or {}
    assert usage.get("input_tokens") == 140000
    assert usage.get("output_tokens") == 1600
    assert usage.get("llm_calls") == 1
