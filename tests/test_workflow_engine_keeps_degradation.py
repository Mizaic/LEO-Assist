"""A later step must never hide that an earlier safety layer degraded.

The engine merged each step's output by plain overwrite for every key
except ``errors``. So when terminology could not reach its service and
set ``degraded=True`` with a ``terminology_lookup_failed`` warning, a
later step (compliance writes ``degraded`` as a plain bool, most steps
return their own ``warnings`` list) replaced both. The trace and the
dry-run report then said "completed" with no warning.

`.cursor/rules/fail-closed-boundary.mdc` rule 1: an unavailable guard
degrades the run. It never finishes as ``completed``.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F (degraded runs routed to human review)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

import pytest

from libs.workflow.engine import ActionDefinition, StepResult, WorkflowEngine

_OUTAGE = "terminology_lookup_failed: we could not reach the terminology service"


def _edge(source: str) -> list[dict[str, str]]:
    return [{"actionId": source, "relationship": "after-end"}]


def _actions() -> list[ActionDefinition]:
    return [
        ActionDefinition(
            action_id="start",
            subgraph_id="trigger",
            trigger_type="",
            trigger_name="",
            node_type="trigger",
            sequence=0,
        ),
        ActionDefinition(
            action_id="terms",
            subgraph_id="terminology",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("start"),
            sequence=1,
        ),
        ActionDefinition(
            action_id="rules",
            subgraph_id="compliance",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("terms"),
            sequence=2,
        ),
    ]


async def _trace(monkeypatch: pytest.MonkeyPatch) -> dict:
    engine = WorkflowEngine()

    async def _execute_step(action: ActionDefinition, _state: dict) -> StepResult:
        if action.subgraph_id == "terminology":
            output = {"warnings": [_OUTAGE], "degraded": True}
        else:
            output = {"warnings": ["compliance_note"], "degraded": False}
        return StepResult(
            action_id=action.action_id,
            subgraph_id=action.subgraph_id,
            status="completed",
            output=output,
        )

    monkeypatch.setattr(engine, "_execute_step", _execute_step)
    result = await engine.trace_run(_actions(), {"errors": []})
    return result["final_state"]


@pytest.mark.asyncio
async def test_a_later_step_cannot_clear_an_earlier_degraded_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = await _trace(monkeypatch)
    assert final.get("degraded") is True, (
        "terminology degraded the run; compliance writing degraded=False "
        "must not make it look healthy"
    )


@pytest.mark.asyncio
async def test_a_later_step_cannot_drop_an_earlier_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = await _trace(monkeypatch)
    warnings = final.get("warnings") or []
    assert _OUTAGE in warnings, f"the outage warning was lost: {warnings!r}"
    assert "compliance_note" in warnings


def test_repeated_warnings_are_kept_once() -> None:
    state: dict = {"warnings": ["w0", "w1"]}
    WorkflowEngine._merge_step_output(state, {"warnings": ["w1", "w2"]})
    assert state["warnings"] == ["w0", "w1", "w2"]
