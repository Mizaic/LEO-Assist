"""Tests for `libs/pipeline_graph/subgraphs/sbar.py`.

The SBAR subgraph is the legacy heuristic SBAR generator wired into the
pipeline canvas. The production SBAR flow lives in the pub/sub orchestrator
(`services.pipeline_worker.app.services.sbar_orchestrator`), but this
subgraph remains the canvas-runnable surface and must:

  - resolve prompts from `state.prompt_configs` first, then registry
  - emit all four SBAR sections (situation/background/assessment/recommendation)
  - degrade gracefully when entities, alerts, recommendations are missing
  - never raise; degraded output goes to the SBAR sections instead

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.sbar import (
    _resolve_sbar_prompts,
    build_sbar_subgraph,
    generate_sbar,
)


class TestResolvePrompts:
    def test_uses_state_prompt_configs_when_present(self):
        state = {
            "prompt_configs": [
                {"name": "sbar_v3", "systemPrompt": "Generate SBAR using v3 rules"},
                {"name": "no_prompt"},
            ]
        }
        prompts = _resolve_sbar_prompts(state)
        assert prompts == {"sbar_v3": "Generate SBAR using v3 rules"}

    def test_falls_back_to_registry_when_no_state_configs(self):
        with patch(
            "libs.prompts.registry.get_prompt",
            return_value="REGISTRY_SBAR_PROMPT",
        ):
            prompts = _resolve_sbar_prompts({})
        assert prompts == {"episode_builder_system": "REGISTRY_SBAR_PROMPT"}

    def test_swallows_registry_errors_and_returns_empty(self):
        with patch(
            "libs.prompts.registry.get_prompt",
            side_effect=KeyError("not found"),
        ):
            prompts = _resolve_sbar_prompts({})
        assert prompts == {}


class TestGenerateSbar:
    def test_emits_all_four_sections(self):
        out = generate_sbar(
            {
                "patient_id": "PAT-1",
                "entities": [
                    {"text": "chest pain"},
                    {"text": "breathlessness"},
                    {"concept_name": "tachycardia"},
                ],
                "safety_net_alerts": [{"id": "ALERT-1"}],
                "recommendations": [{"action": "Refer urgently to cardiology"}],
            }
        )
        report = out["sbar_report"]
        assert set(report.keys()) >= {
            "situation", "background", "assessment", "recommendation",
            "prompt_count",
        }
        sections = out["sbar_sections"]
        assert set(sections.keys()) == {
            "situation", "background", "assessment", "recommendation",
        }

    def test_situation_summarises_first_three_entities(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar(
                {
                    "patient_id": "PAT-2",
                    "entities": [
                        {"text": "chest pain"},
                        {"text": "breathlessness"},
                        {"text": "tachycardia"},
                        {"text": "fourth finding ignored"},
                    ],
                }
            )
        situation = out["sbar_sections"]["situation"]
        assert "chest pain" in situation
        assert "breathlessness" in situation
        assert "tachycardia" in situation
        assert "fourth finding ignored" not in situation

    def test_situation_uses_concept_name_when_text_missing(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar(
                {"entities": [{"concept_name": "asthma"}]}
            )
        assert "asthma" in out["sbar_sections"]["situation"]

    def test_falls_back_to_extracted_when_entities_missing(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar({"extracted": [{"text": "anaemia"}]})
        assert "anaemia" in out["sbar_sections"]["situation"]

    def test_situation_fallback_message_when_no_entities(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar({"patient_id": "PAT-3"})
        assert out["sbar_sections"]["situation"] == "No key findings supplied."

    def test_assessment_counts_alerts_and_recommendations(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar(
                {
                    "safety_net_alerts": [{"id": "A"}, {"id": "B"}],
                    "recommendations": [
                        {"action": "x"}, {"action": "y"}, {"action": "z"}
                    ],
                }
            )
        a = out["sbar_sections"]["assessment"]
        assert "2" in a and "3" in a

    def test_recommendation_takes_first_action(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar(
                {"recommendations": [{"action": "Refer to cardiology"}]}
            )
        assert out["sbar_sections"]["recommendation"] == "Refer to cardiology"

    def test_recommendation_default_when_no_recommendations(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar({})
        assert "monitoring" in out["sbar_sections"]["recommendation"].lower()

    def test_does_not_raise_on_empty_state(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar({})
        assert out["sbar_report"]["situation"]
        assert out["errors"] == []

    def test_propagates_existing_errors(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            out = generate_sbar({"errors": ["upstream failure"]})
        assert out["errors"] == ["upstream failure"]


class TestSubgraphCompiles:
    def test_build_sbar_subgraph_returns_runnable(self):
        graph = build_sbar_subgraph()
        assert hasattr(graph, "invoke")

    def test_subgraph_invoke_produces_sbar_sections(self):
        with patch("libs.prompts.registry.get_prompt", return_value=""):
            graph = build_sbar_subgraph()
            result = graph.invoke(
                {
                    "patient_id": "PAT-9",
                    "entities": [{"text": "headache"}],
                }
            )
        assert "sbar_sections" in result
        assert "headache" in result["sbar_sections"]["situation"]
