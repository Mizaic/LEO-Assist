"""Verification tests for the unified encounter coding agent (VT-LEO-AI-083).

All tests use mocked LLM and tool responses -- no live Bedrock or Neo4j
connection is required. Tests verify: mode detection, tool-loop limits,
backward-compatible audit verdict shape, NER offset presence, kill switches,
and post-processing metadata addition.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

ROOT_CODED: list[dict] = [
    {
        "concept_id": "44054006",
        "term": "Type 2 diabetes mellitus",
        "semantic_tag": "disorder",
        "evidence": "type 2 diabetes",
        "assertion": "present",
        "value": None,
        "unit": None,
        "confidence": 0.95,
    }
]

ENCOUNTER_TEXT = (
    "Patient has type 2 diabetes. Also reports unexplained weight loss for 3 months."
)

AUDIT_VERDICT = {
    "encounter_assessment": "has_issues",
    "missing": [
        {
            "term": "weight loss",
            "severity": "critical",
            "suggested_assertion": "present",
            "reason": "Unexplained weight loss is a cancer red flag.",
            "snomed_search": "weight loss",
            "snomed_concept_id": "89362005",
            "preferred_term": "Weight loss",
            "sentence": "Also reports unexplained weight loss for 3 months.",
            "char_start": 10,
            "char_end": 21,
        }
    ],
    "overcoded": [],
    "wrong_assertion": [],
    "confidence": 0.90,
    "notes": "Missing cancer red flag: unexplained weight loss.",
}


def _make_llm_response(tool_uses=None, text=""):
    """Build a minimal LLMResponse mock."""
    resp = MagicMock()
    resp.text = text
    resp.tool_uses = tool_uses or []
    resp.input_tokens = 1000
    resp.model_id = "test-model"
    return resp


def _submit_verdict_tool_use(verdict: dict) -> dict:
    return {
        "name": "submit_verdict",
        "toolUseId": "tv-001",
        "input": verdict,
    }


# ---------------------------------------------------------------------------
# VT-083-TC-001 / TC-002: mode detection
# ---------------------------------------------------------------------------


def test_load_encounter_audit_mode():
    """VT-083-TC-001: audit mode when coded_entities present."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import load_encounter

    result = load_encounter({
        "encounter_text": ENCOUNTER_TEXT,
        "coded_entities": ROOT_CODED,
        "tier": "big",
    })
    assert result["mode"] == "audit"


def test_load_encounter_code_mode():
    """VT-083-TC-002: code mode when coded_entities empty."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import load_encounter

    result = load_encounter({
        "encounter_text": ENCOUNTER_TEXT,
        "coded_entities": [],
        "tier": "small",
    })
    assert result["mode"] == "code"


def test_load_encounter_code_mode_absent():
    """VT-083-TC-002: code mode when coded_entities absent."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import load_encounter

    result = load_encounter({
        "encounter_text": ENCOUNTER_TEXT,
        "tier": "small",
    })
    assert result["mode"] == "code"


# ---------------------------------------------------------------------------
# VT-083-TC-003: tool iteration limit -> needs_review
# ---------------------------------------------------------------------------


def test_tool_iteration_limit_yields_needs_review():
    """VT-083-TC-003: agent caps tool loop and produces needs_review verdict."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import (
        build_encounter_coding_agent_subgraph,
    )

    search_tool_use = {
        "name": "search_snomed",
        "toolUseId": "s-001",
        "input": {"query": "weight loss"},
    }
    never_submits = _make_llm_response(tool_uses=[search_tool_use])

    with patch("libs.llm_client.factory.create_llm") as mock_create, \
         patch("libs.terminology.client.TerminologyClient") as mock_tc:
        llm_mock = MagicMock()
        llm_mock.converse.return_value = never_submits
        mock_create.return_value = llm_mock
        tc_instance = MagicMock()
        tc_instance.resolve.return_value = {}
        mock_tc.return_value = tc_instance

        with patch.dict(os.environ, {"CODING_AGENT_MAX_ITERATIONS": "2"}):
            # Re-import to pick up env
            import importlib
            import libs.pipeline_graph.subgraphs.encounter_coding_agent as mod
            importlib.reload(mod)
            subgraph = mod.build_encounter_coding_agent_subgraph()

        output = subgraph.invoke({
            "encounter_text": ENCOUNTER_TEXT,
            "coded_entities": ROOT_CODED,
            "tier": "big",
            "apply": False,
        })

    verdict = output.get("verdict") or {}
    assert verdict.get("encounter_assessment") == "needs_review"
    assert float(verdict.get("confidence", 1.0)) == 0.0


# ---------------------------------------------------------------------------
# VT-083-TC-004: audit mode verdict has legacy keys
# ---------------------------------------------------------------------------


def test_audit_mode_verdict_has_legacy_keys():
    """VT-083-TC-004: verdict has missing, overcoded, wrong_assertion keys."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import (
        build_encounter_coding_agent_subgraph,
    )

    submit = _submit_verdict_tool_use(AUDIT_VERDICT)
    resp_with_submit = _make_llm_response(tool_uses=[submit])

    with patch("libs.llm_client.factory.create_llm") as mock_create:
        llm_mock = MagicMock()
        llm_mock.converse.return_value = resp_with_submit
        mock_create.return_value = llm_mock

        subgraph = build_encounter_coding_agent_subgraph()
        output = subgraph.invoke({
            "encounter_text": ENCOUNTER_TEXT,
            "coded_entities": ROOT_CODED,
            "tier": "big",
            "apply": False,
        })

    verdict = output.get("verdict") or {}
    for key in ("missing", "overcoded", "wrong_assertion", "encounter_assessment", "confidence"):
        assert key in verdict, f"Missing legacy key: {key}"


# ---------------------------------------------------------------------------
# VT-083-TC-005: missing entity has sentence and offsets
# ---------------------------------------------------------------------------


def test_missing_entity_has_sentence_and_offsets():
    """VT-083-TC-005: missing entities include sentence, char_start, char_end."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import (
        build_encounter_coding_agent_subgraph,
    )

    submit = _submit_verdict_tool_use(AUDIT_VERDICT)
    resp = _make_llm_response(tool_uses=[submit])

    with patch("libs.llm_client.factory.create_llm") as mock_create:
        llm_mock = MagicMock()
        llm_mock.converse.return_value = resp
        mock_create.return_value = llm_mock

        subgraph = build_encounter_coding_agent_subgraph()
        output = subgraph.invoke({
            "encounter_text": ENCOUNTER_TEXT,
            "coded_entities": ROOT_CODED,
            "tier": "big",
            "apply": False,
        })

    missing = output.get("verdict", {}).get("missing", [])
    assert len(missing) >= 1
    first = missing[0]
    assert "sentence" in first and first["sentence"]
    assert "char_start" in first
    assert "char_end" in first


# ---------------------------------------------------------------------------
# VT-083-TC-006: CODING_AGENT_ENABLED kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_disabled():
    """VT-083-TC-006: CODING_AGENT_ENABLED=false prevents agent availability."""
    with patch.dict(os.environ, {"CODING_AGENT_ENABLED": "false"}):
        import importlib
        import services.coding_worker.app.pipeline.extractor_registry as reg
        importlib.reload(reg)
        provider = reg.AgentExtractorProvider()
        assert not provider.is_available()


# ---------------------------------------------------------------------------
# VT-083-TC-007: runtime provider always apply=False
# ---------------------------------------------------------------------------


def test_agent_extractor_always_apply_false():
    """VT-083-TC-007: AgentExtractorProvider invokes subgraph with apply=False."""
    from services.coding_worker.app.pipeline.extractor_registry import AgentExtractorProvider

    captured = {}

    def fake_invoke(state):
        captured.update(state)
        return {"verdict": {"entities": [], "confidence": 0.9, "encounter_assessment": "coded"}}

    provider = AgentExtractorProvider()
    mock_subgraph = MagicMock()
    mock_subgraph.invoke.side_effect = fake_invoke
    provider._subgraph = mock_subgraph

    provider.extract_batch(ENCOUNTER_TEXT, [])

    assert captured.get("apply") is False
    assert captured.get("coded_entities") == []


# ---------------------------------------------------------------------------
# VT-083-TC-008: unknown tool returns structured error
# ---------------------------------------------------------------------------


def test_unknown_tool_returns_error():
    """VT-083-TC-008: unknown tool call returns ok=False without crashing."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import execute_tools

    state = {
        "encounter_text": ENCOUNTER_TEXT,
        "_pending_tool_uses": [
            {"name": "nonexistent_tool", "toolUseId": "x-001", "input": {}}
        ],
        "messages": [],
        "tool_iterations": 0,
        "verdict": None,
    }
    result = execute_tools(state)
    # Should add a tool result message without raising
    messages = result.get("messages") or []
    assert len(messages) == 1
    content = messages[0]["content"]
    result_text = json.loads(content[0]["toolResult"]["content"][0]["text"])
    assert result_text["ok"] is False
    assert "nonexistent_tool" in result_text["error"]


# ---------------------------------------------------------------------------
# VT-083-TC-009: post_process adds metadata block
# ---------------------------------------------------------------------------


def test_post_process_adds_metadata():
    """VT-083-TC-009: post_process always adds metadata to verdict."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import post_process

    state = {
        "verdict": dict(AUDIT_VERDICT),
        "model_id": "test-model",
        "prompt_version": "v1.0-test",
        "tool_iterations": 3,
        "input_tokens": 3000,
        "output_tokens": 2000,
        "errors": [],
        "messages": [],
    }
    result = post_process(state)
    meta = result["verdict"]["metadata"]
    assert meta["model_id"] == "test-model"
    assert meta["tool_iterations"] == 3
    assert meta["input_tokens"] == 3000
    assert meta["output_tokens"] == 2000
    assert meta["total_tokens"] == 5000
    assert meta["schema_version"] == 1


# ---------------------------------------------------------------------------
# Admin-only prompt rules (reduces false has_issues on workflow notes)
# ---------------------------------------------------------------------------


def test_build_system_prompt_includes_admin_encounter_rules():
    """Both audit and code system prompts carry admin / non-clinical guidance."""
    from libs.prompts.coding_agent_v1 import build_system_prompt

    for mode in ("audit", "code"):
        prompt = build_system_prompt(mode)
        assert "ADMIN / NON-CLINICAL ENCOUNTERS" in prompt
        assert "no_clinical_content" in prompt
        assert "NEVER return \"has_issues\"" in prompt


# ---------------------------------------------------------------------------
# VT-083-TC-010: search_snomed tool
# ---------------------------------------------------------------------------


def test_tool_search_snomed_empty_query():
    """VT-083-TC-010: search_snomed returns ok=False for empty query."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import _tool_search_snomed

    result = _tool_search_snomed({"query": ""})
    assert result["ok"] is False
    assert result["candidates"] == []


def test_tool_search_snomed_valid_query():
    """VT-083-TC-010: search_snomed returns ok=True with candidates list."""
    from libs.pipeline_graph.subgraphs.encounter_coding_agent import _tool_search_snomed

    mock_hit = MagicMock()
    mock_hit.concept_id = "89362005"
    mock_hit.term = "Weight loss"
    mock_hit.semantic_tag = "finding"
    mock_hit.score = 9.1

    target = "libs.pipeline_graph.subgraphs.encounter_coding_agent.TerminologyClient"
    with patch(target) as mock_tc:
        instance = MagicMock()
        instance.resolve.return_value = {"weight loss": [mock_hit]}
        mock_tc.return_value = instance

        result = _tool_search_snomed({"query": "weight loss"})

    assert result["ok"] is True
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["concept_id"] == "89362005"
