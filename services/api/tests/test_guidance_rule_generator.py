"""Tests for GuidanceRuleGenerator and the guidance_rule_extraction subgraph.

Coverage
--------
VT-LEO-AI-064  LLM security compliance
VT-LEO-AI-065  Conservative fail behaviour (no rule on LLM failure)
VT-LEO-AI-066  HITL gate — all rules start as pending_review
VT-LEO-AI-067  Terminology API used for SNOMED coding (not KG full-text index)
VT-LEO-AI-068  Action is extracted and stored as SNOMED procedure
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_driver():
    session = MagicMock()
    session.run.return_value = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = ctx
    return driver, session


def _make_coded_criteria(
    present_resolved=True,
    absent_resolved=False,
    action_resolved=True,
):
    return {
        "present": [
            {
                "term": "rectal bleeding",
                "snomed_concept_id": "405749005" if present_resolved else None,
                "preferred_term": "Rectal haemorrhage",
                "semantic_tag": "finding",
            }
        ],
        "absent": [
            {
                "term": "known colorectal cancer",
                "snomed_concept_id": "363346000" if absent_resolved else None,
                "preferred_term": "Malignant tumour of colon",
                "semantic_tag": "disorder",
            }
        ],
        "action": {
            "term": "suspected cancer pathway referral",
            "snomed_concept_id": "276401003" if action_resolved else None,
            "preferred_term": "Suspected cancer referral",
            "semantic_tag": "procedure",
        },
    }


# ── Subgraph unit tests ────────────────────────────────────────────────────────

class TestResolvePrompt:
    """guidance_rule_extraction subgraph: resolve_prompt node."""

    def test_uses_injected_prompt_config_first(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import resolve_prompt
        result = resolve_prompt({"prompt_config": {"systemPrompt": "CUSTOM PROMPT"}})
        assert result["system_prompt"] == "CUSTOM PROMPT"

    def test_falls_back_to_registry(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import resolve_prompt
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction."
            "libs.prompts.registry.get_prompt",
            return_value="REGISTRY PROMPT",
        ):
            result = resolve_prompt({})
        assert result["system_prompt"] == "REGISTRY PROMPT"

    def test_falls_back_to_inline_constant_on_registry_error(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
            _FALLBACK_SYSTEM_PROMPT,
        )
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction."
            "libs.prompts.registry.get_prompt",
            side_effect=KeyError("not found"),
        ):
            result = resolve_prompt({})
        assert result["system_prompt"] == _FALLBACK_SYSTEM_PROMPT


class TestParseOutput:
    """_parse_llm_output: parsing and security caps."""

    def _parse(self, raw: str):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import _parse_llm_output
        return _parse_llm_output(raw)

    def test_parses_valid_json(self):
        raw = '{"present": ["rectal bleeding"], "absent": [], "action": "2-week-wait referral"}'
        result = self._parse(raw)
        assert result is not None
        assert result["present"] == ["rectal bleeding"]
        assert result["action"] == "2-week-wait referral"

    def test_extracts_json_from_prose(self):
        raw = 'Sure! Here it is: {"present": ["chest X-ray"], "absent": [], "action": null} Done.'
        result = self._parse(raw)
        assert result is not None
        assert result["present"] == ["chest X-ray"]
        assert result["action"] is None

    def test_caps_list_at_5_items(self):
        raw = '{"present": ["a","b","c","d","e","f","g"], "absent": [], "action": null}'
        result = self._parse(raw)
        assert result is not None
        assert len(result["present"]) <= 5

    def test_returns_none_on_invalid_json(self):
        assert self._parse("not json") is None
        assert self._parse("{invalid}") is None

    def test_returns_none_on_empty(self):
        assert self._parse("") is None


class TestCodeSnomed:
    """code_snomed node: Terminology API called with correct semantic_tag filters."""

    def test_criteria_use_finding_disorder_tags(self):
        """present/absent criteria must use clinical finding/disorder tags."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            code_snomed,
            _CRITERIA_TAGS,
        )
        calls = []

        def fake_search(term, tags):
            calls.append((term, tags))
            return {"term": term, "snomed_concept_id": None, "preferred_term": term, "semantic_tag": ""}

        state = {
            "raw_criteria": {
                "present": ["rectal bleeding"],
                "absent":  ["known cancer"],
                "action":  None,
            }
        }
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction._terminology_search",
            side_effect=fake_search,
        ):
            code_snomed(state)

        assert len(calls) == 2  # one for present, one for absent
        for _, tags in calls:
            assert tags == _CRITERIA_TAGS, f"Expected criteria tags, got {tags}"

    def test_action_uses_procedure_tag(self):
        """Action must be looked up with semantic_tag=procedure."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            code_snomed,
            _ACTION_TAGS,
        )
        calls = []

        def fake_search(term, tags):
            calls.append((term, tags))
            return {"term": term, "snomed_concept_id": "123", "preferred_term": term, "semantic_tag": tags[0]}

        state = {
            "raw_criteria": {
                "present": [],
                "absent":  [],
                "action":  "suspected cancer referral",
            }
        }
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction._terminology_search",
            side_effect=fake_search,
        ):
            result = code_snomed(state)

        action_calls = [c for c in calls if c[0] == "suspected cancer referral"]
        assert action_calls, "Action term must be passed to terminology search"
        assert action_calls[0][1] == _ACTION_TAGS

    def test_no_criteria_returns_none(self):
        """No Terminology API calls when raw_criteria is None."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import code_snomed
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction._terminology_search"
        ) as mock_search:
            result = code_snomed({"raw_criteria": None})
        mock_search.assert_not_called()
        assert result["coded_criteria"] is None

    def test_terminology_api_field_name(self):
        """_terminology_search reads snomed_concept_id not conceptId."""
        import httpx
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import _terminology_search

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"snomed_concept_id": "405749005", "term": "Rectal haemorrhage", "semantic_tag": "finding"}
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = _terminology_search("rectal bleeding", ["finding"])

        assert result["snomed_concept_id"] == "405749005", (
            "Must read 'snomed_concept_id' from Terminology API response, not 'conceptId'"
        )


# ── Generator integration tests ────────────────────────────────────────────────

class TestConservativeFail:
    """No rule is written when the LLM or subgraph produces no criteria."""

    def test_no_rule_when_subgraph_returns_none(self):
        """When coded_criteria is None, no Neo4j writes happen."""
        driver, session = _make_driver()
        generator = MagicMock()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": None, "errors": []}

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer for suspected cancer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer"}

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            result = gen.generate_rules_for_guideline("NG12")

        assert result == [], "No rules written when subgraph returns None"
        session.run.assert_not_called()

    def test_no_rule_when_verbatim_empty(self):
        """No rule is generated for recommendations with no verbatim text."""
        driver, session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()

        empty_rec = {"id": "NG12:v1:CH000:R000", "verbatim": "", "title": "", "urgency": "", "strength": ""}
        with patch.object(gen, "_fetch_recommendations", return_value=[empty_rec]):
            result = gen.generate_rules_for_guideline("NG12")

        assert result == []
        gen._subgraph.invoke.assert_not_called()


class TestHitlGate:
    """All generated rules must be written with status=pending_review."""

    def test_rule_written_with_pending_review(self):
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = None  # use inline fallback to control the flow

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer for suspected cancer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "Lung cancer", "chapter_title": "1 Recommendations"}
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_inline_extract", return_value=coded):
                result = gen.generate_rules_for_guideline("NG12")

        assert len(result) == 1, "One rule should be generated"
        all_cypher = " ".join(str(c) for c in session.run.call_args_list)
        assert "pending_review" in all_cypher, "Rule must be written with status pending_review"

    def test_review_task_created(self):
        """A GuidanceReviewTask node is created for each rule."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = None

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer urgently.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}
        coded = _make_coded_criteria()

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_inline_extract", return_value=coded):
                gen.generate_rules_for_guideline("NG12")

        task_calls = [c for c in session.run.call_args_list if "GuidanceReviewTask" in str(c)]
        assert len(task_calls) > 0, "GuidanceReviewTask must be created for HITL queue"


class TestActionGroup:
    """Recommended action is written as a SNOMED procedure ActionGroup."""

    def test_action_group_written_when_resolved(self):
        """ActionGroup and HAS_ACTION edge are created when action has a SNOMED code."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = None

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_inline_extract", return_value=coded):
                gen.generate_rules_for_guideline("NG12")

        action_calls = [c for c in session.run.call_args_list if "ActionGroup" in str(c)]
        assert len(action_calls) > 0, "ActionGroup must be written for the recommended procedure"

    def test_action_group_skipped_when_unresolved(self):
        """No ActionGroup is written when the action has no SNOMED code."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = None

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}
        coded = _make_coded_criteria(present_resolved=True, action_resolved=False)

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_inline_extract", return_value=coded):
                gen.generate_rules_for_guideline("NG12")

        action_calls = [c for c in session.run.call_args_list if "ActionGroup" in str(c)]
        assert len(action_calls) == 0, "ActionGroup must NOT be written when SNOMED code is absent"


class TestSnomedConceptMerge:
    """Concept nodes are MERGED (not just matched) so new SNOMED codes are persisted."""

    def test_concept_node_merged_not_just_matched(self):
        """The Cypher for criteria must use MERGE (concept:SnomedConcept ...) not MATCH."""
        from app.services.guidance_rule_generator import _UPSERT_CONCEPT_AND_CRITERIA
        assert "MERGE (concept:SnomedConcept" in _UPSERT_CONCEPT_AND_CRITERIA, (
            "Concept nodes must be MERGEd so that SNOMED codes returned by "
            "the Terminology API are persisted even if not yet in the KG"
        )
        assert "MATCH (concept" not in _UPSERT_CONCEPT_AND_CRITERIA, (
            "Must not use bare MATCH for concept — that would silently skip "
            "concepts not already in the graph"
        )
