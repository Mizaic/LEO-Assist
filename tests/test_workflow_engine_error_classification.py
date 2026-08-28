"""Site 6: a KeyError inside a subgraph is not a missing registration.

`_execute_step` wrapped the registry lookup AND the subgraph run in one
`except KeyError`, so a KeyError raised by clinical logic inside the
subgraph was reported as "Unknown subgraph". Triage then chased a
deployment problem while the real coding defect stayed hidden.

`libs/workflow/engine.py` is the older orchestrator and is still live, so
these tests also pin the behaviour that must NOT change.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.workflow.engine import ActionDefinition, WorkflowEngine


def _action(subgraph_id: str = "post_processing") -> ActionDefinition:
    return ActionDefinition(
        action_id="post",
        subgraph_id=subgraph_id,
        trigger_type="named-event",
        trigger_name="coding_requested",
    )


class _StubGraph:
    def __init__(
        self, result: dict[str, Any] | None = None, raises: Exception | None = None
    ):
        self._result = result or {}
        self._raises = raises

    def invoke(self, _state: dict[str, Any]) -> dict[str, Any]:
        if self._raises is not None:
            raise self._raises
        return self._result


class _StubRegistry:
    def __init__(self, graph: Any = None, build_error: Exception | None = None):
        self._graph = graph
        self._build_error = build_error

    def build(self, _subgraph_id: str, **_kwargs: Any) -> Any:
        if self._build_error is not None:
            raise self._build_error
        return self._graph


def _engine(registry: Any) -> WorkflowEngine:
    engine = WorkflowEngine()
    engine._registry = registry  # type: ignore[assignment]
    return engine


# ---------------------------------------------------------------------------
# Happy paths -- correct behaviour must not change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_step_reports_entities_and_tokens() -> None:
    graph = _StubGraph(
        {
            "processed_entities": [{"text": "chest pain"}, {"text": "cough"}],
            "is_verified": True,
            "llm_tokens": {
                "input_tokens": 120,
                "output_tokens": 40,
                "cost_usd": 0.002,
                "prompt_name": "extraction_v1",
                "prompt_version": 3,
                "provider": "aws",
                "few_shot_example_ids": ["fs-1", "fs-2"],
            },
        }
    )
    result = await _engine(_StubRegistry(graph))._execute_step(
        _action(), {"patient_id": "p1"}
    )

    assert result.status == "completed"
    assert result.error is None
    assert result.entity_count == 2
    assert result.is_verified is True
    assert result.llm_input_tokens == 120
    assert result.llm_output_tokens == 40
    assert result.llm_prompt_name == "extraction_v1"
    assert result.llm_prompt_version == 3
    assert result.llm_provider == "aws"
    assert result.llm_few_shot_example_ids == ["fs-1", "fs-2"]


@pytest.mark.asyncio
async def test_missing_registration_is_still_reported_as_unknown_subgraph() -> None:
    """A genuinely unregistered subgraph must keep its existing message."""
    registry = _StubRegistry(build_error=KeyError("Subgraph 'ghost' not registered"))
    result = await _engine(registry)._execute_step(
        _action("ghost"), {"patient_id": "p1"}
    )

    assert result.status == "error"
    assert result.error == "Unknown subgraph: ghost"


# ---------------------------------------------------------------------------
# Site 6 -- a KeyError from inside the subgraph is a different fault
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyerror_inside_subgraph_is_not_a_missing_registration() -> None:
    graph = _StubGraph(raises=KeyError("entities"))
    result = await _engine(_StubRegistry(graph))._execute_step(
        _action(), {"patient_id": "p1"}
    )

    assert result.status == "error"
    assert "Unknown subgraph" not in (result.error or "")


@pytest.mark.asyncio
async def test_keyerror_inside_subgraph_names_the_missing_key() -> None:
    """Triage needs the key and the subgraph, not a deployment red herring."""
    graph = _StubGraph(raises=KeyError("entities"))
    result = await _engine(_StubRegistry(graph))._execute_step(
        _action(), {"patient_id": "p1"}
    )

    assert "KeyError" in (result.error or "")
    assert "entities" in (result.error or "")
    assert "post_processing" in (result.error or "")


@pytest.mark.asyncio
async def test_other_exceptions_inside_subgraph_keep_their_message() -> None:
    graph = _StubGraph(raises=RuntimeError("scope guard exploded"))
    result = await _engine(_StubRegistry(graph))._execute_step(
        _action(), {"patient_id": "p1"}
    )

    assert result.status == "error"
    assert result.error == "scope guard exploded"
