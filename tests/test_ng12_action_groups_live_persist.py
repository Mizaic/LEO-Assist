"""Live Neo4j persist for NG12 preferred-fallback / either-or action groups.

Unlike the Playwright walkthroughs (which stub the guidance API), this
test calls ``apply_rule_edit`` against the knowledge graph so the edited
rules become ``active`` and show under approved guidelines.

Requires local env (KnowledgeGraphClient + Aura). Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_ng12_action_groups_live_persist.py -v

Atlas: DI-42246DA7 / DO-F8C56339
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from libs.neo4j_client.client import KnowledgeGraphClient
from services.api.app.services.guidance_rule_edit import (
    LogicCriterion,
    LogicNode,
    RuleAction,
    RuleUpdates,
    apply_rule_edit,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write approved NG12 action-group rules.",
)

_FIND_PRED = """
MATCH (g:Guideline {id: 'NG12'})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE r.title = $title AND r.versionId = 'NG12:v2'
MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE rule.status IN ['pending_review', 'active']
RETURN rule.id AS rule_id, rule.status AS status
ORDER BY CASE rule.status WHEN 'pending_review' THEN 0 ELSE 1 END,
         coalesce(rule.updatedAt, rule.createdAt) DESC
LIMIT 1
"""

_VERIFY = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
RETURN rule.id AS rule_id,
       rule.status AS status,
       rule.actionJson AS action_json
"""


def _crit(concept_id: str, term: str, tag: str = "procedure") -> LogicCriterion:
    return LogicCriterion(
        snomed_concept_id=concept_id,
        preferred_term=term,
        semantic_tag=tag,
        term=term,
    )


def _action(
    concept_id: str,
    term: str,
    strength: str,
    *,
    group_id: str,
    group_mode: str,
    group_rank: int,
) -> RuleAction:
    return RuleAction(
        criterion=_crit(concept_id, term),
        strength=strength,
        group_id=group_id,
        group_mode=group_mode,
        group_rank=group_rank,
    )


def _logic_and(children: list[LogicNode]) -> LogicNode:
    return LogicNode(kind="AND", children=children)


def _demo_age(years: int) -> LogicNode:
    return LogicNode(
        kind="DEMOGRAPHIC",
        field="age",
        operator=">=",
        value=float(years),
        unit="years",
    )


def _concept_leaf(concept_id: str, term: str, tag: str) -> LogicNode:
    return LogicNode(
        kind="CONCEPT",
        criterion=_crit(concept_id, term, tag),
    )


def _nss_trio(group_id: str, strength: str) -> list[RuleAction]:
    # Referral arms use real UK FTR concepts whose preferred/FSN term
    # starts with "Fast track referral". Urgent investigation stays a
    # CT procedure (not an FTR) to match NICE "urgent investigation".
    return [
        _action(
            "419394006",
            "Computed tomography of abdomen and pelvis",
            strength,
            group_id=group_id,
            group_mode="any",
            group_rank=0,
        ),
        _action(
            "38661000000100",
            "Fast track referral",
            strength,
            group_id=group_id,
            group_mode="any",
            group_rank=1,
        ),
        _action(
            "1556551000000104",
            "Fast track referral for suspected cancer due to non-site-specific symptoms",
            strength,
            group_id=group_id,
            group_mode="any",
            group_rank=2,
        ),
    ]


SCENARIOS: list[dict[str, Any]] = [
    {
        "title": "1.2.5",
        "reason": "Live persist: NG12 1.2.5 CT preferred, ultrasound if CT not available.",
        "name": "NG12 1.2.5 -- CT or ultrasound if CT unavailable",
        "priority": "urgent",
        "due_days": 14,
        "logic_tree": _logic_and(
            [
                _demo_age(60),
                _concept_leaf(
                    "422868009",
                    "Unexplained weight loss",
                    "finding",
                ),
            ]
        ),
        "actions": [
            _action(
                "419394006",
                "Computed tomography of abdomen and pelvis",
                "consider",
                group_id="ng12-1-2-5",
                group_mode="preferred_fallback",
                group_rank=0,
            ),
            _action(
                "418394000",
                "Ultrasound scan of abdomen and pelvis",
                "consider",
                group_id="ng12-1-2-5",
                group_mode="preferred_fallback",
                group_rank=1,
            ),
        ],
        "expected_mode": "preferred_fallback",
    },
    {
        "title": "1.9.1",
        "reason": "Live persist: NG12 1.9.1 MRI preferred, CT if MRI contraindicated.",
        "name": "NG12 1.9.1 -- MRI brain or CT if contraindicated",
        "priority": "urgent",
        "due_days": 14,
        "logic_tree": _logic_and(
            [
                _demo_age(18),
                _concept_leaf(
                    "230690007",
                    "Cerebrovascular accident",
                    "disorder",
                ),
            ]
        ),
        "actions": [
            _action(
                "816077007",
                "Magnetic resonance imaging of brain",
                "consider",
                group_id="ng12-1-9-1",
                group_mode="preferred_fallback",
                group_rank=0,
            ),
            _action(
                "303653007",
                "Computed tomography of head",
                "consider",
                group_id="ng12-1-9-1",
                group_mode="preferred_fallback",
                group_rank=1,
            ),
        ],
        "expected_mode": "preferred_fallback",
    },
    {
        "title": "1.13.2",
        "reason": "Live persist: NG12 1.13.2 either/or urgent referral, 2WW, or NSS.",
        "name": "NG12 1.13.2 -- unexplained weight loss NSS triad",
        "priority": "urgent",
        "due_days": 14,
        "logic_tree": _logic_and(
            [
                _demo_age(60),
                _concept_leaf(
                    "422868009",
                    "Unexplained weight loss",
                    "finding",
                ),
            ]
        ),
        "actions": _nss_trio("ng12-1-13-2", "offer"),
        "expected_mode": "any",
    },
    {
        "title": "1.13.3",
        "reason": "Live persist: NG12 1.13.3 either/or urgent referral, 2WW, or NSS.",
        "name": "NG12 1.13.3 -- unexplained appetite loss NSS triad",
        "priority": "urgent",
        "due_days": 14,
        "logic_tree": _logic_and(
            [
                _concept_leaf("79890006", "Loss of appetite", "finding"),
            ]
        ),
        "actions": _nss_trio("ng12-1-13-3", "offer"),
        "expected_mode": "any",
    },
    {
        "title": "1.13.4",
        "reason": "Live persist: NG12 1.13.4 either/or consider urgent referral, 2WW, or NSS.",
        "name": "NG12 1.13.4 -- DVT NSS triad",
        "priority": "urgent",
        "due_days": 14,
        "logic_tree": _logic_and(
            [
                _concept_leaf("128053003", "Deep venous thrombosis", "disorder"),
            ]
        ),
        "actions": _nss_trio("ng12-1-13-4", "consider"),
        "expected_mode": "any",
    },
]


@pytest.fixture(scope="module")
def kg_client():
    client = KnowledgeGraphClient()
    yield client
    client.close()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["title"])
def test_persist_ng12_action_group_rule(kg_client, scenario: dict[str, Any]):
    pred_rows = kg_client.run(_FIND_PRED, title=scenario["title"])
    assert pred_rows, f"No pending/active predecessor for {scenario['title']}"
    predecessor_id = pred_rows[0]["rule_id"]

    updates = RuleUpdates(
        name=scenario["name"],
        logic_tree=scenario["logic_tree"],
        actions=scenario["actions"],
        priority=scenario["priority"],
        due_days=scenario["due_days"],
    )
    result = apply_rule_edit(
        kg_client,
        predecessor_rule_id=predecessor_id,
        updates=updates,
        reviewer="live_persist_pytest",
        reason=scenario["reason"],
    )
    new_id = result["rule_id"]
    assert new_id != predecessor_id

    rows = kg_client.run(_VERIFY, rule_id=new_id)
    assert rows, f"Edited rule missing: {new_id}"
    row = rows[0]
    assert row["status"] == "active"
    payload = json.loads(row["action_json"])
    assert isinstance(payload, list)
    assert len(payload) == len(scenario["actions"])
    modes = {item.get("group_mode") for item in payload}
    assert modes == {scenario["expected_mode"]}
    assert all(item.get("group_id") for item in payload)
    ranks = sorted(item.get("group_rank") for item in payload)
    assert ranks == list(range(len(payload)))
