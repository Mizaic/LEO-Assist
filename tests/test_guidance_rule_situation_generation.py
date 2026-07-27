"""Generator + extraction wiring for situation-aligned NICE drafts.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
    _normalise_to_logic_tree,
)


def test_fetch_recommendations_query_includes_list_structure():
    from app.services.guidance_rule_generator import _FETCH_RECOMMENDATIONS

    assert "listStructureJson" in _FETCH_RECOMMENDATIONS
    assert "list_structure_json" in _FETCH_RECOMMENDATIONS


def test_empty_logic_tree_writes_four_pathway_shells_for_structured_rec():
    from app.services.guidance_rule_generator import GuidanceRuleGenerator

    fixture = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "situation_skeleton_parity.json"
        ).read_text()
    )
    case = next(c for c in fixture["cases"] if c["id"] == "ng12_1_2_9_structure")
    # Use four situations for the plan's 1.2.9-style stub acceptance.
    text = "Lead: A, or B, or C, or D."
    structure = {
        "lead_text": "Lead: ",
        "items": [
            {"text": "A", "start": 6, "end": 7},
            {"text": "B", "start": 12, "end": 13},
            {"text": "C", "start": 18, "end": 19},
            {"text": "D", "start": 24, "end": 25},
        ],
    }
    gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
    tree = gen._empty_logic_tree(
        {
            "verbatim": text,
            "list_structure_json": json.dumps(structure),
            "title": "1.2.9",
        }
    )
    assert tree["kind"] == "OR"
    assert len(tree["children"]) == 4
    assert all(c.get("pathway_key") for c in tree["children"])
    # Keep the full 6-item structure case green too.
    tree6 = gen._empty_logic_tree(
        {
            "verbatim": case["text"],
            "list_structure_json": json.dumps(case["structure"]),
        }
    )
    assert tree6["kind"] == "OR"
    assert len(tree6["children"]) == 6


def test_subgraph_invoke_receives_list_structure_and_triage():
    from app.services.guidance_rule_generator import GuidanceRuleGenerator

    gen = GuidanceRuleGenerator.__new__(GuidanceRuleGenerator)
    gen._driver = MagicMock()
    gen._subgraph = MagicMock()
    gen._subgraph.invoke.return_value = {
        "raw_criteria": {
            "schema_version": 2,
            "logic_tree": {"kind": "AND", "children": []},
        },
        "coded_criteria": {
            "schema_version": 2,
            "logic_tree": {"kind": "AND", "children": []},
            "actions": [],
        },
        "errors": [],
        "llm_tokens": {},
    }
    gen._write_rule = MagicMock(return_value="rule:test:1")
    gen._write_guidance_audit_event = MagicMock()

    structure = {"lead_text": "x", "items": [{"text": "a", "start": 0, "end": 1}]}
    rec = {
        "id": "NG12:v1:R1",
        "verbatim": "Refer people aged 40 and over with unexplained haemoptysis.",
        "title": "1.1.1",
        "urgency": "urgent_2w",
        "strength": "refer",
        "list_structure_json": json.dumps(structure),
    }
    rule_id = gen._generate_one("NG12", rec)
    assert rule_id == "rule:test:1"
    kwargs = gen._subgraph.invoke.call_args[0][0]
    assert kwargs["triage_bucket"] == "full_rule"
    assert kwargs["recommendation"]["list_structure"] == structure


def test_trigger_plus_narrative_forces_narrative_actions():
    from app.services.guidance_rule_generator import GuidanceRuleGenerator

    coded = {
        "schema_version": 2,
        "logic_tree": {"kind": "AND", "children": []},
        "actions": [
            {
                "text": "advise skin care",
                "search_terms": ["skin care"],
                "snomed_concept_id": "123",
                "strength": "discuss",
            }
        ],
    }
    out = GuidanceRuleGenerator._force_narrative_actions(coded)
    assert out["actions"][0]["action_kind"] == "narrative"
    assert out["actions"][0]["action_text"] == "advise skin care"
    assert out["actions"][0].get("criterion") is None


def test_situation_draft_normalise_preserves_or_arity():
    payload = {
        "schema_version": 2,
        "prerequisites": [
            {
                "kind": "demographic",
                "field": "age",
                "operator": ">=",
                "value": 55,
                "unit": "years",
            }
        ],
        "situations": [
            {
                "text": "dyspepsia",
                "source": "structure",
                "conditions": [{"kind": "concept", "term": {"text": "dyspepsia"}}],
            },
            {
                "text": "weight loss",
                "source": "structure",
                "conditions": [{"kind": "concept", "term": {"text": "weight loss"}}],
            },
            {
                "text": "thrombocytosis",
                "source": "structure",
                "conditions": [{"kind": "concept", "term": {"text": "thrombocytosis"}}],
            },
            {
                "text": "nausea",
                "source": "structure",
                "conditions": [{"kind": "concept", "term": {"text": "nausea"}}],
            },
        ],
        "actions": [
            {
                "text": "direct access upper gastrointestinal endoscopy",
                "search_terms": ["OGD"],
                "strength": "consider",
            }
        ],
    }
    out = _normalise_to_logic_tree(payload)
    assert out is not None
    or_node = out["logic_tree"]["children"][1]
    assert or_node["kind"] == "OR"
    assert len(or_node["children"]) == 4
    assert len(out["situation_windows"]) == 4
