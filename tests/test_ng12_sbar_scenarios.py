"""NG12 SBAR output golden-set tests.

Tests `call_recommendation` with a mocked LLM invoker against three
scenarios sourced from `tests/fixtures/ng12_test_scenarios.json`.

What is tested:
  1. When a matched rule is passed as `assessment_rules`, the recommendation
     section references the clinical action (e.g. chest X-ray, referral).
  2. Actions are returned as a non-empty list when at least one rule fires.
  3. When no rules fire, the action list is empty.
  4. The invoker is always called exactly once per `call_recommendation` call.
  5. LLM error responses are translated gracefully (error key propagated).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any
from unittest.mock import AsyncMock

import pytest

from libs.sbar.prompt_calls import call_recommendation

_FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "ng12_test_scenarios.json"
)

_ALL_SBAR_SCENARIOS: list[dict] = json.loads(
    _FIXTURE_PATH.read_text()
)["sbar_scenarios"]


def _stub_prompt_fetcher(name: str) -> str:
    """Return a minimal system prompt stub that avoids Neo4j at test time."""
    return (
        f"You are a clinical decision support system generating the {name} "
        "section of an SBAR report. Use the provided context only."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_invoker(
    markdown: str,
    actions: list[dict] | None = None,
) -> AsyncMock:
    """Return an async invoker mock that returns the given recommendation."""
    mock = AsyncMock(return_value={
        "recommendation_markdown": markdown,
        "actions": actions or [],
    })
    return mock


# ---------------------------------------------------------------------------
# Parametrised: rules-fire scenarios
# ---------------------------------------------------------------------------

def _fire_scenario_ids(scenarios: list[dict]) -> list[str]:
    return [s["id"] for s in scenarios if s.get("assessment_rules")]


@pytest.mark.parametrize(
    "scenario",
    [s for s in _ALL_SBAR_SCENARIOS if s.get("assessment_rules")],
    ids=_fire_scenario_ids(_ALL_SBAR_SCENARIOS),
)
def test_sbar_recommendation_mentions_expected_keywords(
    scenario: dict,
) -> None:
    """When a rule fires the recommendation markdown must mention key terms."""
    expected_keywords = scenario.get("expected_sbar_keywords", [])
    min_actions = scenario.get("expected_min_action_count", 0)

    # Build markdown that contains the expected keywords
    simulated_md = (
        "Based on the clinical presentation and matched guideline rules, "
        + ", ".join(expected_keywords or ["a clinical action is recommended"])
        + " within 2 weeks."
    )
    simulated_actions = [
        {"description": "Urgent investigation", "priority": "urgent"}
    ] * max(min_actions, 1)

    invoker = _make_invoker(simulated_md, simulated_actions)

    result = asyncio.get_event_loop().run_until_complete(
        call_recommendation(
            situation_md=scenario["situation_md"],
            background_md=scenario["background_md"],
            assessment_md=scenario["assessment_md"],
            assessment_rules=scenario["assessment_rules"],
            guideline_titles=scenario["guideline_titles"],
            guidelines=scenario["guidelines"],
            patient_id="test-patient",
                prompt_fetcher=_stub_prompt_fetcher,
            invoker=invoker,
        )
    )

    assert result["error"] is None, (
        f"{scenario['id']}: unexpected error: {result['error']}"
    )
    assert result["markdown"], (
        f"{scenario['id']}: recommendation markdown must not be empty"
    )

    md_lower = result["markdown"].lower()
    for kw in expected_keywords:
        assert kw.lower() in md_lower, (
            f"{scenario['id']}: expected keyword '{kw}' not found in "
            f"recommendation markdown"
        )

    assert len(result["actions"]) >= min_actions, (
        f"{scenario['id']}: expected at least {min_actions} action(s), "
        f"got {len(result['actions'])}"
    )


# ---------------------------------------------------------------------------
# No rules fire -- empty action list
# ---------------------------------------------------------------------------

def test_no_rules_fire_produces_no_actions() -> None:
    """When assessment_rules is empty the recommendation must have no actions."""
    scenario = next(
        s for s in _ALL_SBAR_SCENARIOS if s["id"] == "NG12-SBAR-003"
    )
    max_actions = scenario.get("expected_max_action_count", 0)

    invoker = _make_invoker(
        "No suspected cancer pathway referral is indicated based on the "
        "current evidence. Continue routine monitoring.",
        actions=[],
    )

    result = asyncio.get_event_loop().run_until_complete(
        call_recommendation(
            situation_md=scenario["situation_md"],
            background_md=scenario["background_md"],
            assessment_md=scenario["assessment_md"],
            assessment_rules=scenario["assessment_rules"],
            guideline_titles=scenario["guideline_titles"],
            guidelines=scenario["guidelines"],
            patient_id="test-patient",
                prompt_fetcher=_stub_prompt_fetcher,
            invoker=invoker,
        )
    )

    assert result["error"] is None
    assert len(result["actions"]) <= max_actions, (
        f"Expected at most {max_actions} action(s) when no rules fire, "
        f"got {len(result['actions'])}"
    )


# ---------------------------------------------------------------------------
# Invoker called exactly once per call_recommendation
# ---------------------------------------------------------------------------

def test_invoker_called_exactly_once_per_recommendation() -> None:
    """call_recommendation must invoke the LLM exactly one time."""
    invoker = _make_invoker(
        "Urgent chest X-ray within 2 weeks is recommended."
    )
    mesothelioma_scenario = next(
        s for s in _ALL_SBAR_SCENARIOS if s["id"] == "NG12-SBAR-001"
    )

    asyncio.get_event_loop().run_until_complete(
        call_recommendation(
            situation_md=mesothelioma_scenario["situation_md"],
            background_md=mesothelioma_scenario["background_md"],
            assessment_md=mesothelioma_scenario["assessment_md"],
            assessment_rules=mesothelioma_scenario["assessment_rules"],
            guideline_titles=mesothelioma_scenario["guideline_titles"],
            guidelines=mesothelioma_scenario["guidelines"],
            patient_id="test-patient",
                prompt_fetcher=_stub_prompt_fetcher,
            invoker=invoker,
        )
    )

    invoker.assert_awaited_once()


# ---------------------------------------------------------------------------
# LLM error response handled gracefully
# ---------------------------------------------------------------------------

def test_llm_error_response_is_surfaced_cleanly() -> None:
    """An LLM error response must not raise; it must populate error fields."""
    error_invoker = AsyncMock(return_value={"error": "rate_limit"})
    mesothelioma_scenario = next(
        s for s in _ALL_SBAR_SCENARIOS if s["id"] == "NG12-SBAR-001"
    )

    result = asyncio.get_event_loop().run_until_complete(
        call_recommendation(
            situation_md=mesothelioma_scenario["situation_md"],
            background_md=mesothelioma_scenario["background_md"],
            assessment_md=mesothelioma_scenario["assessment_md"],
            assessment_rules=mesothelioma_scenario["assessment_rules"],
            guideline_titles=mesothelioma_scenario["guideline_titles"],
            guidelines=mesothelioma_scenario["guidelines"],
            patient_id="test-patient",
                prompt_fetcher=_stub_prompt_fetcher,
            invoker=error_invoker,
        )
    )

    assert result["error"] is not None, (
        "Error response from LLM must propagate the error field"
    )
    assert result["markdown"] == ""


# ---------------------------------------------------------------------------
# Assessment rules context forwarding
# ---------------------------------------------------------------------------

def test_assessment_rules_included_in_invoker_call() -> None:
    """The rule_id from assessment_rules must appear in the user prompt."""
    captured_args: list[Any] = []

    async def capturing_invoker(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured_args.extend(args)
        return {
            "recommendation_markdown": "Refer urgently.",
            "actions": [{"description": "Refer to colorectal", "priority": "urgent"}],
        }

    rectal_scenario = next(
        s for s in _ALL_SBAR_SCENARIOS if s["id"] == "NG12-SBAR-002"
    )

    asyncio.get_event_loop().run_until_complete(
        call_recommendation(
            situation_md=rectal_scenario["situation_md"],
            background_md=rectal_scenario["background_md"],
            assessment_md=rectal_scenario["assessment_md"],
            assessment_rules=rectal_scenario["assessment_rules"],
            guideline_titles=rectal_scenario["guideline_titles"],
            guidelines=rectal_scenario["guidelines"],
            patient_id="test-patient",
                prompt_fetcher=_stub_prompt_fetcher,
            invoker=capturing_invoker,
        )
    )

    assert captured_args, "invoker must have been called"
    # The user prompt is the second positional argument to invoker
    user_prompt: str = captured_args[1] if len(captured_args) > 1 else ""
    expected_rule_id = rectal_scenario["assessment_rules"][0]["rule_id"]
    assert expected_rule_id in user_prompt, (
        f"Rule ID '{expected_rule_id}' must appear in the user prompt "
        f"so the LLM has the rule context"
    )
