"""Tests for GuidanceRuleGenerator and the guidance_rule_extraction subgraph.

Coverage
--------
VT-LEO-AI-064  LLM security compliance
VT-LEO-AI-065  Failed extractions write pending_review stubs for HITL
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
    action_resolved=True,
):
    return {
        "schema_version": 2,
        "logic_tree": {
            "kind": "AND",
            "node_id": "n1",
            "children": [
                {
                    "kind": "concept",
                    "criterion": {
                        "node_id": "n2",
                        "term": "rectal bleeding",
                        "snomed_concept_id": "405749005" if present_resolved else None,
                        "preferred_term": "Rectal haemorrhage",
                        "semantic_tag": "finding",
                    },
                }
            ],
        },
        "action": {
            "term": "suspected cancer pathway referral",
            "snomed_concept_id": "276401003" if action_resolved else None,
            "preferred_term": "Suspected cancer referral",
            "semantic_tag": "procedure",
        },
        "verifier": {"overall_status": "verified"},
    }


# ── Subgraph unit tests ────────────────────────────────────────────────────────


class TestResolvePrompt:
    """guidance_rule_extraction subgraph: resolve_prompt node."""

    def test_uses_injected_prompt_config_first(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
        )

        result = resolve_prompt({"prompt_config": {"systemPrompt": "CUSTOM PROMPT"}})
        assert result["system_prompt"] == "CUSTOM PROMPT"

    def test_uses_per_guideline_prompt(self):
        """resolve_prompt tries guideline-specific name before _default."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
        )

        calls = []

        def _get_prompt(name, version=1):
            calls.append(name)
            if name == "guidance_rule_extraction_NG12":
                return "NG12 SPECIFIC PROMPT", []
            raise RuntimeError("not found")

        with patch(
            "libs.prompts.registry.get_prompt_with_few_shot", side_effect=_get_prompt
        ):
            result = resolve_prompt({"guideline_id": "NG12:v1:CH002:SEC000:R000"})

        assert result["system_prompt"] == "NG12 SPECIFIC PROMPT"
        assert "guidance_rule_extraction_NG12" in calls

    def test_falls_back_to_default_when_specific_missing(self):
        """resolve_prompt falls back to _default when guideline-specific prompt absent."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
        )

        def _get_prompt(name, version=1):
            if name == "guidance_rule_extraction_default":
                return "DEFAULT PROMPT", []
            raise RuntimeError("not found")

        with patch(
            "libs.prompts.registry.get_prompt_with_few_shot", side_effect=_get_prompt
        ):
            result = resolve_prompt({"guideline_id": "NG151:v1"})

        assert result["system_prompt"] == "DEFAULT PROMPT"

    def test_returns_empty_and_error_when_all_missing(self):
        """When no prompt found in Neo4j, system_prompt is empty and error is recorded."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
        )

        with patch(
            "libs.prompts.registry.get_prompt_with_few_shot",
            side_effect=RuntimeError("not found"),
        ):
            result = resolve_prompt({"guideline_id": "NG999:v1"})

        assert result["system_prompt"] == ""
        assert any("prompt_missing" in e for e in result.get("errors", []))


class TestParseOutput:
    """_parse_llm_output: parsing, normalisation, and security caps."""

    def _parse(self, raw: str):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            _parse_llm_output,
        )

        return _parse_llm_output(raw)

    def test_parses_logic_tree_format(self):
        raw = '{"schema_version":2,"logic_tree":{"kind":"AND","children":[{"kind":"concept","term":{"text":"rectal bleeding"}}]},"action":{"text":"2ww referral","search_terms":["2ww referral"]}}'
        result = self._parse(raw)
        assert result is not None
        assert result["schema_version"] == 2
        assert result["logic_tree"]["kind"] == "AND"
        assert result["actions"][0]["text"] == "2ww referral"

    def test_old_present_absent_format_normalised_to_criteria_groups(self):
        """Old format converted: present → ALL group, absent → NOT group."""
        raw = '{"present": ["rectal bleeding"], "absent": ["active cancer"], "action": "2ww referral"}'
        result = self._parse(raw)
        assert result is not None
        assert result["schema_version"] == 2
        assert result["logic_tree"]["kind"] == "AND"
        assert result["actions"][0]["text"] == "2ww referral"

    def test_extracts_json_from_prose(self):
        raw = 'Sure! Here it is: {"schema_version":2,"logic_tree":{"kind":"OR","children":[{"kind":"concept","term":{"text":"chest X-ray"}}]},"action":null} Done.'
        result = self._parse(raw)
        assert result is not None
        assert result["actions"] == []

    def test_assigns_node_ids(self):
        raw = '{"schema_version":2,"logic_tree":{"kind":"OR","children":[{"kind":"concept","term":{"text":"a"}},{"kind":"concept","term":{"text":"b"}}]},"action":null}'
        result = self._parse(raw)
        assert result is not None
        assert result["logic_tree"]["node_id"]
        assert result["logic_tree"]["children"][0]["node_id"]

    def test_returns_none_on_invalid_json(self):
        assert self._parse("not json") is None
        assert self._parse("{invalid}") is None

    def test_returns_none_on_empty(self):
        assert self._parse("") is None

    def test_invalid_mode_defaults_to_all(self):
        raw = '{"criteria_groups": [{"mode": "UNKNOWN", "terms": ["cough"]}], "action": null}'
        result = self._parse(raw)
        assert result is not None
        assert result["logic_tree"]["kind"] == "AND"


class TestGuidancePromptHeuristics:
    def test_vague_symptom_phrase_detection(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _looks_like_vague_symptom_clause,
        )

        assert _looks_like_vague_symptom_clause(
            "Take into account any associated symptoms, particularly fever and weight loss."
        )
        assert not _looks_like_vague_symptom_clause("Refer people with dysphagia.")

    def test_instruction_issue_detection(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _has_instruction_issue,
        )

        verifier_result = {
            "overall_status": "rejected",
            "leaf_decisions": [
                {
                    "node_id": "n1",
                    "status": "rejected",
                    "reason": "JSON format invalid for required schema.",
                },
            ],
            "action_decision": {"status": "not_required", "reason": "No action"},
        }
        assert _has_instruction_issue(verifier_result)


class TestCodeSnomed:
    """code_snomed node: batched terminology resolve produces candidate payloads."""

    def test_batched_resolve_populates_candidate_tree(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import code_snomed

        state = {
            "raw_criteria": {
                "schema_version": 2,
                "logic_tree": {
                    "kind": "AND",
                    "node_id": "n1",
                    "children": [
                        {
                            "kind": "concept",
                            "node_id": "n2",
                            "term": {
                                "text": "rectal bleeding",
                                "search_terms": ["rectal bleeding"],
                            },
                        }
                    ],
                },
                "actions": [
                    {
                        "text": "suspected cancer referral",
                        "search_terms": ["suspected cancer referral"],
                    }
                ],
            }
        }

        with patch("libs.terminology.client.TerminologyClient.resolve") as mock_resolve:
            mock_resolve.return_value = {
                "rectal bleeding": [
                    MagicMock(
                        concept_id="405749005",
                        term="Rectal haemorrhage",
                        semantic_tag="finding",
                        score=0.9,
                        read_code=None,
                        raw={},
                    )
                ],
                "suspected cancer referral": [
                    MagicMock(
                        concept_id="123",
                        term="Suspected cancer referral",
                        semantic_tag="procedure",
                        score=0.9,
                        read_code=None,
                        raw={},
                    )
                ],
            }
            result = code_snomed(state)

        assert result["candidate_criteria"] is not None
        leaf = result["candidate_criteria"]["logic_tree"]["children"][0]["criterion"]
        assert leaf["candidates"][0]["concept_id"] == "405749005"
        assert (
            result["candidate_criteria"]["actions"][0]["candidates"][0]["concept_id"]
            == "123"
        )

    def test_no_criteria_returns_none(self):
        """No Terminology API calls when raw_criteria is None."""
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import code_snomed

        result = code_snomed({"raw_criteria": None})
        assert result["candidate_criteria"] is None

    def test_terminology_api_failure_routes_to_hitl_with_no_candidates(self):
        """Conservative-fail invariant: when Terminology API resolves nothing
        and the agentic resolver can't recover, the term is routed to HITL
        with zero candidates -- no rule is silently auto-coded.

        Earlier versions of this test asserted ``candidate_criteria is None``.
        The contract now produces a populated structure with empty candidate
        lists and a non-empty ``hitl_terms`` so downstream code can route the
        term for human review (the conservative-fail still holds because the
        rule writer flags the rule as ``partial`` when ``needs_human_review``).
        """
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import code_snomed

        empty_agentic = {
            "selected": None,
            "needs_human_review": True,
            "resolver_turns": 1,
            "best_candidates": [],
            "search_history": [["x"]],
            "reason": "stubbed for unit test",
        }
        with (
            patch("libs.terminology.client.TerminologyClient.resolve", return_value={}),
            patch(
                "libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl."
                "_run_agentic_resolver",
                return_value=empty_agentic,
            ),
        ):
            result = code_snomed(
                {
                    "raw_criteria": {
                        "schema_version": 2,
                        "logic_tree": None,
                        "actions": [{"text": "x", "search_terms": ["x"]}],
                    }
                }
            )

        candidate = result["candidate_criteria"]
        assert (
            candidate is not None
        ), "expected a populated candidate_criteria so HITL routing can fire"
        actions = candidate.get("actions") or []
        assert actions, "expected the action to still be present, unresolved"
        action = actions[0]
        assert (
            action.get("candidates") == []
        ), "no SNOMED candidates should be selected when Terminology returns nothing"
        assert float(action.get("confidence") or 0.0) == 0.0
        hitl_terms = candidate.get("hitl_terms") or []
        assert hitl_terms, "expected the unresolved term to be routed to HITL"
        assert any(t.get("kind") == "action" for t in hitl_terms)


# ── Generator integration tests ────────────────────────────────────────────────


class TestGenerationStub:
    """Failed extractions still write pending_review stubs for manual authoring."""

    def test_stub_when_subgraph_returns_none(self):
        """When coded_criteria is None, a pending_review stub is written."""
        driver, session = _make_driver()
        generator = MagicMock()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": None,
            "coded_criteria": None,
            "errors": ["llm_error:timeout"],
        }

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer for suspected cancer.",
            "title": "1.1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_write_guidance_audit_event"):
                result = gen.generate_rules_for_guideline("NG12")

        assert len(result) == 1
        assert result[0].startswith("rule:NG12:v1:CH000:R000:")
        upsert_calls = [
            c for c in session.run.call_args_list if "AppropriatenessRule" in str(c)
        ]
        assert upsert_calls, "Expected AppropriatenessRule upsert on extraction failure"

    def test_stub_when_no_rule_expected(self):
        """Process-only recommendations still appear in the review queue."""
        driver, session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": {
                "no_rule_expected": True,
                "reason": "service_configuration_only",
            },
            "errors": [],
        }

        rec = {
            "id": "NG12:v1:CH003:R004",
            "verbatim": "Ensure local pathways exist.",
            "title": "1.3.4",
            "urgency": "routine",
            "strength": "offer",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            with patch.object(gen, "_write_guidance_audit_event"):
                result = gen.generate_rules_for_guideline("NG12")

        assert len(result) == 1
        assert session.run.call_count >= 1

    def test_no_rule_when_verbatim_empty(self):
        """No rule is generated for recommendations with no verbatim text."""
        driver, session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()

        empty_rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "",
            "title": "",
            "urgency": "",
            "strength": "",
        }
        with patch.object(gen, "_fetch_recommendations", return_value=[empty_rec]):
            result = gen.generate_rules_for_guideline("NG12")

        assert result == []
        gen._subgraph.invoke.assert_not_called()

    def test_only_without_rules_skips_existing(self):
        """Generation can target only recommendations with no linked rule."""
        driver, _session = _make_driver()
        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": {}},
            "coded_criteria": {
                "schema_version": 2,
                "logic_tree": {"type": "ALL", "children": []},
                "criteria_groups": [],
                "action": None,
            },
            "errors": [],
        }

        recs = [
            {
                "id": "NG12:v1:CH000:R000",
                "verbatim": "Refer for suspected cancer.",
                "title": "1.1.1",
                "urgency": "urgent_2w",
                "strength": "refer",
                "has_rule": True,
            },
            {
                "id": "NG12:v1:CH000:R001",
                "verbatim": "Offer urgent chest X-ray for suspected lung cancer.",
                "title": "1.1.2",
                "urgency": "urgent_2w",
                "strength": "offer",
                "has_rule": False,
            },
        ]

        with patch.object(gen, "_fetch_recommendations", return_value=recs):
            with patch.object(
                gen, "_write_rule", return_value="rule:test"
            ) as write_rule:
                result = gen.generate_rules_for_guideline(
                    "NG12",
                    only_without_rules=True,
                )

        assert result == ["rule:test"]
        assert gen._subgraph.invoke.call_count == 1
        assert write_rule.call_count == 1


class TestHitlGate:
    """All generated rules must be written with status=pending_review."""

    def test_rule_written_with_pending_review(self):
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": coded,
            "errors": [],
        }

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer for suspected cancer.",
            "title": "1.1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
            "section_title": "Lung cancer",
            "chapter_title": "1 Recommendations",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            result = gen.generate_rules_for_guideline("NG12")

        assert len(result) == 1, "One rule should be generated"
        all_cypher = " ".join(str(c) for c in session.run.call_args_list)
        assert (
            "pending_review" in all_cypher
        ), "Rule must be written with status pending_review"

    def test_review_task_created(self):
        """A GuidanceReviewTask node is created for each rule."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria()
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": coded,
            "errors": [],
        }

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer urgently.",
            "title": "1.1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
            "section_title": "",
            "chapter_title": "",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            gen.generate_rules_for_guideline("NG12")

        task_calls = [
            c for c in session.run.call_args_list if "GuidanceReviewTask" in str(c)
        ]
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
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": coded,
            "errors": [],
        }

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer.",
            "title": "1.1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
            "section_title": "",
            "chapter_title": "",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            gen.generate_rules_for_guideline("NG12")

        action_calls = [
            c for c in session.run.call_args_list if "ActionGroup" in str(c)
        ]
        assert (
            len(action_calls) > 0
        ), "ActionGroup must be written for the recommended procedure"

    def test_action_group_skipped_when_unresolved(self):
        """No ActionGroup is written when the action has no SNOMED code."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria(present_resolved=True, action_resolved=False)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": coded,
            "errors": [],
        }

        rec = {
            "id": "NG12:v1:CH000:R000",
            "verbatim": "Refer.",
            "title": "1.1.1",
            "urgency": "urgent_2w",
            "strength": "refer",
            "section_title": "",
            "chapter_title": "",
        }

        with patch.object(gen, "_fetch_recommendations", return_value=[rec]):
            gen.generate_rules_for_guideline("NG12")

        action_calls = [
            c for c in session.run.call_args_list if "ActionGroup" in str(c)
        ]
        assert (
            len(action_calls) == 0
        ), "ActionGroup must NOT be written when SNOMED code is absent"


class TestCanonicalConceptMerge:
    """Concept nodes are MERGED into the CANONICAL `:Concept {id}` graph
    (not the legacy parallel `:SnomedConcept {conceptId}` namespace) so
    every guidance node shares identity with terminology search results
    and with the SNOMED loader's IS_A hierarchy.

    See DI-LEO-AI-528 + scripts/migrations/2026_link_or_delete_orphan_
    snomed_concepts.py for the wider schema-unification work that this
    test pins in place.
    """

    def test_criteria_concept_merged_on_canonical_label(self):
        from app.services.guidance_rule_generator import _UPSERT_CONCEPT_AND_CRITERIA

        # New canonical write -- single source of truth.
        assert "MERGE (concept:Concept {id: $concept_id})" in _UPSERT_CONCEPT_AND_CRITERIA
        # Legacy parallel namespace MUST NOT be reintroduced.
        assert ":SnomedConcept" not in _UPSERT_CONCEPT_AND_CRITERIA, (
            "Generator must not write the legacy :SnomedConcept label -- "
            "see DI-LEO-AI-528."
        )
        # Property names must match the SNOMED loader so terminology
        # search and guidance reads project the same fields.
        assert "concept.preferred_term" in _UPSERT_CONCEPT_AND_CRITERIA
        assert "concept.semantic_tag" in _UPSERT_CONCEPT_AND_CRITERIA
        # Bare MATCH would silently skip newly-coded SNOMED ids.
        assert "MATCH (concept" not in _UPSERT_CONCEPT_AND_CRITERIA

    def test_action_concept_merged_on_canonical_label_no_procedure_subtype(self):
        from app.services.guidance_rule_generator import _UPSERT_ACTION_CONCEPT

        assert "MERGE (proc:Concept {id: $concept_id})" in _UPSERT_ACTION_CONCEPT
        assert ":SnomedConcept" not in _UPSERT_ACTION_CONCEPT
        # The legacy generator wrote (:SnomedConcept:Procedure ...) which
        # polluted the canonical `:Concept` graph with sub-labels. The
        # bitmap compiler binds action targets unlabeled (HAS_ACTION is
        # the constraint), so dropping :Procedure is safe and necessary.
        assert ":Procedure" not in _UPSERT_ACTION_CONCEPT
        assert "proc.preferred_term" in _UPSERT_ACTION_CONCEPT

    def test_applies_to_concept_merged_on_canonical_label(self):
        from app.services.guidance_rule_generator import _UPSERT_APPLIES_TO

        assert "MERGE (concept:Concept {id: $concept_id})" in _UPSERT_APPLIES_TO
        assert ":SnomedConcept" not in _UPSERT_APPLIES_TO
        assert "concept.preferred_term" in _UPSERT_APPLIES_TO


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
                sess,
                "rule:test:123",
                [criterion],
                group_type="ALL",
                predicate="PRESENT",
            )

        # Check that distance_child=1, distance_parent=0 were passed to session.run
        all_call_kwargs = [str(c) for c in sess.run.call_args_list]
        distance_kwarg_found = any("distance_child" in s for s in all_call_kwargs)
        assert (
            distance_kwarg_found
        ), "distance_child must be passed to session.run() in _write_criteria_group"

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
                sess,
                "rule:test:123",
                action,
                priority_meta={"priority": "2ww", "due_days": 14},
            )

        all_call_kwargs = [str(c) for c in sess.run.call_args_list]
        priority_passed = any("'2ww'" in s or "2ww" in s for s in all_call_kwargs)
        assert (
            priority_passed
        ), "priority='2ww' must be passed to session.run() in _write_action_group"

    def test_write_rule_derives_priority_from_urgency(self):
        """_write_rule extracts urgency from rec and passes derived priority to action group."""
        driver, session = _make_driver()

        from app.services.guidance_rule_generator import GuidanceRuleGenerator

        gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
        gen._driver = driver
        coded = _make_coded_criteria(present_resolved=True, action_resolved=True)
        gen._subgraph = MagicMock()
        gen._subgraph.invoke.return_value = {
            "raw_criteria": {"logic_tree": None},
            "coded_criteria": coded,
            "errors": [],
        }

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


class TestPromptVersionPreference:
    def test_resolve_prompt_prefers_v2_when_available(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
            resolve_prompt,
        )

        seen = []

        def _get_prompt(name, version=1):
            seen.append((name, version))
            if name == "guidance_rule_extraction_NG12" and version == 2:
                return "NG12 V2 PROMPT", []
            raise RuntimeError("not found")

        with patch(
            "libs.prompts.registry.get_prompt_with_few_shot", side_effect=_get_prompt
        ):
            result = resolve_prompt({"guideline_id": "NG12:v1:CH002:SEC000:R000"})

        assert result["system_prompt"] == "NG12 V2 PROMPT"
        assert ("guidance_rule_extraction_NG12", 2) in seen


class TestActionFallbackPolicy:
    def test_select_action_candidate_allows_upper_gi_fallback_for_stomach(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _select_action_candidate,
        )

        rec = {
            "urgency": "urgent_2w",
            "section_title": "Stomach cancer",
            "verbatim": "Offer a fast track referral for suspected stomach cancer.",
        }
        selected, reason = _select_action_candidate(
            rec,
            "fast track referral for suspected stomach cancer",
            [
                {
                    "concept_id": "ugi",
                    "preferred_term": "Fast track referral for suspected upper gastrointestinal cancer",
                    "semantic_tag": "procedure",
                    "score": 0.7,
                },
                {
                    "concept_id": "generic",
                    "preferred_term": "Urgent referral",
                    "semantic_tag": "procedure",
                    "score": 0.95,
                },
            ],
            verifier_choice=None,
        )

        assert selected is not None
        assert selected["concept_id"] == "ugi"
        assert "fallback" in (reason or "").lower()

    def test_select_action_candidate_rejects_urgent_for_routine_referral(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _select_action_candidate,
        )

        rec = {
            "urgency": "routine",
            "section_title": "Bladder cancer",
            "verbatim": "Consider a non-urgent referral for suspected bladder cancer.",
        }
        selected, _ = _select_action_candidate(
            rec,
            "non-urgent referral for suspected bladder cancer",
            [
                {
                    "concept_id": "fasttrack",
                    "preferred_term": "Fast track referral for suspected urological cancer",
                    "semantic_tag": "procedure",
                    "score": 0.99,
                }
            ],
            verifier_choice=None,
        )

        assert selected is None

    def test_expand_action_search_terms_adds_non_urgent_variants(self):
        """Three invariants the variant-expander must preserve:

        1. The original term is always present.
        2. A ``routine`` urgency-synonym variant exists for the same organ.
        3. An organ-class generalisation exists ("urological cancer" for
           bladder), so SNOMED resolution can fall back from the specific
           organ to the broader cancer pathway when needed.

        The earlier assertion expected "non-urgent referral for suspected
        urological cancer" specifically. The current contract emits
        organ-class variants with urgency markers (e.g. "fast track
        referral for suspected urological cancer") rather than the
        non-urgent prefix, so we assert on the *presence* of the
        urological-cancer fallback rather than its exact wording.
        """
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _expand_action_search_terms,
        )

        terms = _expand_action_search_terms(
            "non-urgent referral for suspected bladder cancer",
            "Consider a non-urgent referral for suspected bladder cancer.",
        )
        assert "non-urgent referral for suspected bladder cancer" in terms
        assert "routine referral for suspected bladder cancer" in terms
        assert any("urological cancer" in t for t in terms), (
            "expected at least one organ-class fallback variant containing "
            f"'urological cancer'; got: {terms}"
        )


class TestRetrySearchTemplates:
    def test_retry_search_adds_ultrasound_uncertainty_templates(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _rerun_requested_searches,
        )

        candidate_criteria = {
            "logic_tree": {
                "kind": "concept",
                "criterion": {
                    "node_id": "n1",
                    "term": "uncertain ultrasound findings",
                    "candidates": [],
                },
            },
            "action": None,
        }
        verifier_result = {
            "leaf_decisions": [
                {
                    "node_id": "n1",
                    "status": "retry_search",
                    "reason": "No candidate adequately captures uncertain or indeterminate ultrasound findings.",
                    "retry_search_terms": [],
                }
            ],
            "action_decision": {"status": "not_required"},
        }

        seen_terms = []

        def _fake_resolve(terms, expected_tags=None):
            seen_terms.extend(terms)
            return {term: [] for term in terms}

        with patch(
            "libs.terminology.client.TerminologyClient.resolve",
            side_effect=_fake_resolve,
        ):
            _rerun_requested_searches(candidate_criteria, verifier_result)

        assert "indeterminate ultrasound finding" in seen_terms
        assert "equivocal ultrasound scan finding" in seen_terms

    def test_retry_search_adds_skin_suspicion_templates(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _rerun_requested_searches,
        )

        candidate_criteria = {
            "logic_tree": {
                "kind": "concept",
                "criterion": {
                    "node_id": "n1",
                    "term": "skin lesion raising suspicion of squamous cell carcinoma",
                    "candidates": [],
                },
            },
            "action": None,
        }
        verifier_result = {
            "leaf_decisions": [
                {
                    "node_id": "n1",
                    "status": "retry_search",
                    "reason": "A finding-level suspicious skin lesion concept is required.",
                    "retry_search_terms": [],
                }
            ],
            "action_decision": {"status": "not_required"},
        }

        seen_terms = []

        def _fake_resolve(terms, expected_tags=None):
            seen_terms.extend(terms)
            return {term: [] for term in terms}

        with patch(
            "libs.terminology.client.TerminologyClient.resolve",
            side_effect=_fake_resolve,
        ):
            _rerun_requested_searches(candidate_criteria, verifier_result)

        assert "suspicious skin lesion" in seen_terms
        assert "skin lesion suspicious for squamous cell carcinoma" in seen_terms


class TestAgenticExpansionAndPartial:
    def test_classify_leaf_difficulty(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            _classify_leaf_difficulty,
        )

        assert (
            _classify_leaf_difficulty("chest signs compatible with pleural disease")
            == "abstract_phrase"
        )
        assert _classify_leaf_difficulty("new-onset diabetes") == "temporal_modifier"
        assert (
            _classify_leaf_difficulty("FIT result >= 10 micrograms per gram")
            == "quantitative"
        )
        assert (
            _classify_leaf_difficulty("results of blood tests suggest myeloma")
            == "composite_pattern"
        )
        assert _classify_leaf_difficulty("vulval lump") == "narrow_body_site"
        assert _classify_leaf_difficulty("haemoptysis") == "concrete"

    def test_expand_leaves_adds_traceability_metadata(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            expand_leaves,
        )

        state = {
            "recommendation": {"verbatim": "Refer for suspected oesophageal cancer"},
            "raw_criteria": {
                "schema_version": 2,
                "logic_tree": {
                    "kind": "concept",
                    "node_id": "n1",
                    "term": {
                        "text": "chest signs compatible with pleural disease",
                        "search_terms": [],
                    },
                },
                "actions": [
                    {
                        "text": "fast track referral for suspected oesophageal cancer",
                        "search_terms": [],
                    }
                ],
            },
        }
        # The semantic-expansion LLM call is out of scope for this unit test
        # (it needs live Bedrock credentials); stub it so the deterministic
        # variant-expansion path is exercised without a network dependency.
        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl."
            "_run_small_to_big_expansion_tool_loop",
            return_value=["signs of pleural effusion (llm)"],
        ):
            out = expand_leaves(state)
        expanded = out["expanded_criteria"]
        term = expanded["logic_tree"]["term"]
        action = expanded["actions"][0]
        assert term["original_phrase"] == "chest signs compatible with pleural disease"
        assert term["expansion_source"] == "abstract_phrase+semantic_llm"
        assert "pleural disease signs" in term["search_terms"]
        assert (
            "fast track referral for suspected upper gastrointestinal cancer"
            in action["search_terms"]
        )

    def test_agentic_resolve_marks_hitl_after_three_turns(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            agentic_resolve,
        )

        state = {
            "recommendation": {"verbatim": "Refer for suspected thyroid cancer"},
            "candidate_criteria": {
                "schema_version": 2,
                "logic_tree": {
                    "kind": "concept",
                    "criterion": {
                        "node_id": "n1",
                        "term": "lip lump",
                        "candidates": [],
                    },
                },
                "action": {
                    "term": "fast track referral for suspected thyroid cancer",
                    "candidates": [],
                },
            },
        }

        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl._run_agentic_resolver",
            return_value={
                "selected": None,
                "needs_human_review": True,
                "resolver_turns": 3,
                "best_candidates": [],
                "search_history": [["a"], ["b"], ["c"]],
                "reason": "No safe match after 3 turns; requires human review.",
            },
        ):
            out = agentic_resolve(state)

        assert out["agentic_terms"]
        assert any(e.startswith("needs_human_review:") for e in out["errors"])
        leaf = out["candidate_criteria"]["logic_tree"]["criterion"]
        assert leaf["needs_human_review"] is True
        assert leaf["resolver_turns"] == 3

    def test_assemble_result_returns_partial_when_hitl_exists(self):
        from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
            assemble_result,
        )

        state = {
            "candidate_criteria": {
                "schema_version": 2,
                "logic_tree": {
                    "kind": "concept",
                    "criterion": {
                        "node_id": "n1",
                        "term": "lip lump",
                        "candidates": [],
                    },
                },
                "action": None,
            },
            "agentic_terms": [
                {
                    "kind": "leaf",
                    "node_id": "n1",
                    "term": "lip lump",
                    "reason": "No safe match after 3 turns; requires human review.",
                    "search_history": [["a"], ["b"], ["c"]],
                    "best_candidates": [],
                }
            ],
            "errors": ["needs_human_review:leaf:n1"],
            "llm_tokens": {},
        }

        with patch(
            "libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl.verify_codes",
            return_value={
                "coded_criteria": None,
                "errors": ["needs_human_review:leaf:n1"],
                "llm_tokens": {},
            },
        ):
            out = assemble_result(state)

        assert out["coded_criteria"] is not None
        assert out["coded_criteria"]["needs_human_review"] is True
        assert out["coded_criteria"]["hitl_terms"]
