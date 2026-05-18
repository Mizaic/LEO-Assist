"""SBAR recommendation wiring for 348 NG12 scenarios (mock LLM)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from libs.sbar.prompt_calls import call_recommendation

from tests.helpers.ng12_scenario_loader import load_paired_scenarios
from tests.test_ng12_sbar_scenarios import _stub_prompt_fetcher

_, _, _SBR_DOC = load_paired_scenarios()
_SBAR_SCENARIOS: list[dict] = _SBR_DOC["scenarios"]


def _invoker_for(scenario: dict) -> AsyncMock:
    kws = scenario.get("expected_sbar_keywords") or ["review"]
    md = "Plan: " + ", ".join(kws) + " within 2 weeks."
    min_ac = int(scenario.get("expected_min_action_count") or 0)
    if min_ac <= 0:
        actions: list[dict] = []
    else:
        actions = [
            {"description": "Clinical follow-up", "priority": "routine"}
        ] * min_ac
    return AsyncMock(return_value={"recommendation_markdown": md, "actions": actions})


def test_sbar_rows_mock_llm_keyword_coverage() -> None:
    """Every SBAR row can render without Neo4j and mentions expected keywords."""
    for scenario in _SBAR_SCENARIOS:
        invoker = _invoker_for(scenario)
        result = asyncio.get_event_loop().run_until_complete(
            call_recommendation(
                situation_md=scenario["situation_md"],
                background_md=scenario["background_md"],
                assessment_md=scenario["assessment_md"],
                assessment_rules=scenario.get("assessment_rules") or [],
                guideline_titles=scenario["guideline_titles"],
                guidelines=scenario["guidelines"],
                patient_id="fixture-scan",
                prompt_fetcher=_stub_prompt_fetcher,
                invoker=invoker,
            )
        )
        assert result.get("error") is None, scenario["id"]
        md = (result.get("markdown") or "").lower()
        for kw in scenario.get("expected_sbar_keywords") or []:
            assert kw.lower() in md, f"{scenario['id']} missing {kw}"
        min_a = int(scenario.get("expected_min_action_count") or 0)
        assert len(result.get("actions") or []) >= min_a, scenario["id"]
