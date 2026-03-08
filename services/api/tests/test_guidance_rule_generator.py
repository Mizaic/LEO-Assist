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
        "criteria_groups": [
            {
                "mode": "ALL",
                "coded_terms": [
                    {
                        "term": "rectal bleeding",
                        "snomed_concept_id": "405749005" if present_resolved else None,
                        "preferred_term": "Rectal haemorrhage",
                        "semantic_tag": "finding",
                    }
                ],
            },
            {
                "mode": "NOT",
                "coded_terms": [
                    {
                        "term": "known colorectal cancer",
                        "snomed_concept_id": "363346000" if absent_resolved else None,
                        "preferred_term": "Malignant tumour of colon",
                        "semantic_tag": "disorder",
                    }
                ],
            },
        ],
        "applies_to": [],
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

    def test_uses_per_guideline_prompt(self):
        """resolve_prompt tries guideline-specific name before _default."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import resolve_prompt

        calls = []

        def _get_prompt(name, version=1):
            calls.append(name)
            if name == "guidance_rule_extraction_NG12":
                return "NG12 SPECIFIC PROMPT"
            raise RuntimeError("not found")

        with patch("libs.prompts.registry.get_prompt", side_effect=_get_prompt):
            result = resolve_prompt({"guideline_id": "NG12:v1:CH002:SEC000:R000"})

        assert result["system_prompt"] == "NG12 SPECIFIC PROMPT"
        assert "guidance_rule_extraction_NG12" in calls

    def test_falls_back_to_default_when_specific_missing(self):
        """resolve_prompt falls back to _default when guideline-specific prompt absent."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import resolve_prompt

        def _get_prompt(name, version=1):
            if name == "guidance_rule_extraction_default":
                return "DEFAULT PROMPT"
            raise RuntimeError("not found")

        with patch("libs.prompts.registry.get_prompt", side_effect=_get_prompt):
            result = resolve_prompt({"guideline_id": "NG151:v1"})

        assert result["system_prompt"] == "DEFAULT PROMPT"

    def test_returns_empty_and_error_when_all_missing(self):
        """When no prompt found in Neo4j, system_prompt is empty and error is recorded."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import resolve_prompt

        with patch("libs.prompts.registry.get_prompt", side_effect=RuntimeError("not found")):
            result = resolve_prompt({"guideline_id": "NG999:v1"})

        assert result["system_prompt"] == ""
        assert any("prompt_missing" in e for e in result.get("errors", []))


class TestParseOutput:
    """_parse_llm_output: parsing, normalisation, and security caps."""

    def _parse(self, raw: str):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import _parse_llm_output
        return _parse_llm_output(raw)

    def test_parses_new_criteria_groups_format(self):
        raw = '{"criteria_groups": [{"mode": "ALL", "terms": ["rectal bleeding"]}], "action": "2ww referral"}'
        result = self._parse(raw)
        assert result is not None
        assert "criteria_groups" in result
        assert result["criteria_groups"][0]["mode"] == "ALL"
        assert "rectal bleeding" in result["criteria_groups"][0]["terms"]
        assert result["action"] == "2ww referral"

    def test_old_present_absent_format_normalised_to_criteria_groups(self):
        """Old format converted: present → ALL group, absent → NOT group."""
        raw = '{"present": ["rectal bleeding"], "absent": ["active cancer"], "action": "2ww referral"}'
        result = self._parse(raw)
        assert result is not None
        assert "criteria_groups" in result
        modes = {g["mode"] for g in result["criteria_groups"]}
        assert "ALL" in modes
        assert "NOT" in modes
        all_terms = [t for g in result["criteria_groups"] for t in g["terms"]]
        assert "rectal bleeding" in all_terms
        assert "active cancer" in all_terms
        assert result["action"] == "2ww referral"

    def test_extracts_json_from_prose(self):
        raw = 'Sure! Here it is: {"criteria_groups": [{"mode": "ANY", "terms": ["chest X-ray"]}], "action": null} Done.'
        result = self._parse(raw)
        assert result is not None
        assert result["action"] is None

    def test_caps_terms_at_5_items(self):
        raw = '{"criteria_groups": [{"mode": "ANY", "terms": ["a","b","c","d","e","f","g"]}], "action": null}'
        result = self._parse(raw)
        assert result is not None
        assert len(result["criteria_groups"][0]["terms"]) <= 5

    def test_returns_none_on_invalid_json(self):
        assert self._parse("not json") is None
        assert self._parse("{invalid}") is None

    def test_returns_none_on_empty(self):
        assert self._parse("") is None

    def test_invalid_mode_defaults_to_all(self):
        raw = '{"criteria_groups": [{"mode": "UNKNOWN", "terms": ["cough"]}], "action": null}'
        result = self._parse(raw)
        assert result is not None
        assert result["criteria_groups"][0]["mode"] == "ALL"


class TestCodeSnomed:
    """code_snomed node: Terminology API called with correct semantic_tag filters."""

    def test_criteria_use_finding_disorder_tags(self):
        """Criteria terms in criteria_groups must use clinical finding/disorder tags."""
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
                "criteria_groups": [
                    {"mode": "ALL", "terms": ["rectal bleeding"]},
                    {"mode": "NOT", "terms": ["known cancer"]},
                ],
                "action": None,
            }
        }
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction._terminology_search",
            side_effect=fake_search,
        ):
            code_snomed(state)

        assert len(calls) == 2  # one for each clinical term
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
                "criteria_groups": [],
                "action": "suspected cancer referral",
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
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": coded, "errors": []}

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer for suspected cancer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "Lung cancer", "chapter_title": "1 Recommendations"}

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
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
        coded = _make_coded_criteria()
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": coded, "errors": []}

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer urgently.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
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
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": coded, "errors": []}

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            gen.generate_rules_for_guideline("NG12")

        action_calls = [c for c in session.run.call_args_list if "ActionGroup" in str(c)]
        assert len(action_calls) > 0, "ActionGroup must be written for the recommended procedure"

    def test_action_group_skipped_when_unresolved(self):
        """No ActionGroup is written when the action has no SNOMED code."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria(present_resolved=True, action_resolved=False)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": coded, "errors": []}

        rec = {"id": "NG12:v1:CH000:R000", "verbatim": "Refer.", "title": "1.1.1", "urgency": "urgent_2w", "strength": "refer", "section_title": "", "chapter_title": ""}

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
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


class TestDistanceOnCriteriaEdge:
    """HAS_CRITERIA edge must carry distanceChild and distanceParent properties."""

    def test_cypher_stores_distance_params(self):
        """_UPSERT_CONCEPT_AND_CRITERIA uses $distance_child and $distance_parent."""
        from app.services.guidance_rule_generator import _UPSERT_CONCEPT_AND_CRITERIA
        assert "$distance_child" in _UPSERT_CONCEPT_AND_CRITERIA
        assert "$distance_parent" in _UPSERT_CONCEPT_AND_CRITERIA

    def test_cypher_sets_distance_on_edge(self):
        """The HAS_CRITERIA edge creation sets e.distanceChild and e.distanceParent."""
        from app.services.guidance_rule_generator import _UPSERT_CONCEPT_AND_CRITERIA
        assert "e.distanceChild" in _UPSERT_CONCEPT_AND_CRITERIA
        assert "e.distanceParent" in _UPSERT_CONCEPT_AND_CRITERIA

    def test_write_criteria_group_passes_distance_to_cypher(self):
        """_write_criteria_group passes distance values to session.run()."""
        driver, session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver

        criterion = {
            "term": "haematuria",
            "snomed_concept_id": "34436003",
            "preferred_term": "Haematuria",
            "semantic_tag": "finding",
        }
        with driver.session() as sess:
            gen._write_criteria_group(
                sess, "rule:test:123",
                [criterion], group_type="ALL", predicate="PRESENT",
            )

        # Check that distance_child=1, distance_parent=0 were passed to session.run
        all_call_kwargs = [str(c) for c in sess.run.call_args_list]
        distance_kwarg_found = any("distance_child" in s for s in all_call_kwargs)
        assert distance_kwarg_found, (
            "distance_child must be passed to session.run() in _write_criteria_group"
        )

    def test_default_distance_child_is_three(self):
        """Default distanceChild=3 so bitmap matches descendants up to 3 IS_A hops."""
        from app.services.guidance_rule_generator import _DEFAULT_DISTANCE_CHILD
        assert _DEFAULT_DISTANCE_CHILD == 3, (
            "distanceChild default should be 3 to cover GP coding subtypes "
            "(e.g. 'haematuria' → 'microscopic haematuria' within 3 IS_A hops)"
        )


class TestActionPriorityOnEdge:
    """HAS_ACTION edge must carry priority and dueDays from the recommendation urgency."""

    def test_urgency_2w_maps_to_2ww_priority(self):
        """urgent_2w urgency maps to priority='2ww' and due_days=14."""
        from app.services.guidance_rule_generator import _urgency_to_priority
        result = _urgency_to_priority("urgent_2w")
        assert result["priority"] == "2ww"
        assert result["due_days"] == 14

    def test_urgency_immediate_maps_to_urgent(self):
        from app.services.guidance_rule_generator import _urgency_to_priority
        result = _urgency_to_priority("immediate")
        assert result["priority"] == "urgent"
        assert result["due_days"] == 1

    def test_urgency_very_urgent_48h(self):
        from app.services.guidance_rule_generator import _urgency_to_priority
        result = _urgency_to_priority("very_urgent_48h")
        assert result["priority"] == "urgent"
        assert result["due_days"] == 2

    def test_urgency_routine_has_no_due_days(self):
        from app.services.guidance_rule_generator import _urgency_to_priority
        result = _urgency_to_priority("routine")
        assert result["priority"] == "routine"
        assert result["due_days"] is None

    def test_unknown_urgency_defaults_to_routine(self):
        from app.services.guidance_rule_generator import _urgency_to_priority
        result = _urgency_to_priority(None)
        assert result["priority"] == "routine"

    def test_cypher_stores_priority_on_action_edge(self):
        """_UPSERT_ACTION_CONCEPT must set ha.priority and ha.dueDays."""
        from app.services.guidance_rule_generator import _UPSERT_ACTION_CONCEPT
        assert "ha.priority" in _UPSERT_ACTION_CONCEPT
        assert "ha.dueDays" in _UPSERT_ACTION_CONCEPT

    def test_write_action_group_passes_priority_to_cypher(self):
        """_write_action_group passes priority/due_days to session.run()."""
        driver, session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver

        action = {
            "term": "suspected cancer referral",
            "snomed_concept_id": "306206005",
            "preferred_term": "Suspected cancer referral",
            "semantic_tag": "procedure",
        }
        with driver.session() as sess:
            gen._write_action_group(
                sess, "rule:test:123", action,
                priority_meta={"priority": "2ww", "due_days": 14},
            )

        all_call_kwargs = [str(c) for c in sess.run.call_args_list]
        priority_passed = any("'2ww'" in s or "2ww" in s for s in all_call_kwargs)
        assert priority_passed, "priority='2ww' must be passed to session.run() in _write_action_group"

    def test_write_rule_derives_priority_from_urgency(self):
        """_write_rule extracts urgency from rec and passes derived priority to action group."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator
        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {"coded_criteria": coded, "errors": []}

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer urgently.",
            "title": "1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
            "section_title": "",
            "chapter_title": "",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_write_action_group") as mock_action:
                gen.generate_rules_for_guideline("NG12")

        assert mock_action.called, "_write_action_group should be called"
        _, _, _, priority_meta = mock_action.call_args.args
        assert priority_meta["priority"] == "2ww"
        assert priority_meta["due_days"] == 14
