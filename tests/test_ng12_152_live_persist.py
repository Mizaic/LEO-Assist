"""Live persist: exclude vulval-site pain from NG12 1.5.2.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_ng12_152_live_persist.py -v

Atlas: DI-185DE0CE, DO-5899D7BE, VT-2082C55B, UN-5F3BF083.
"""

from __future__ import annotations

import json
import os

import pytest

from libs.guidelines.ng12_152_pelvic_pain import (
    PELVIC_PAIN_ID,
    VULVAL_PAIN_ID,
    exclude_vulval_site_from_pelvic_leaf,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from services.api.app.services.guidance_rule_edit import LogicNode, RuleUpdates, apply_rule_edit

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write the 1.5.2 exclusion.",
)

_FIND = """
MATCH (r:AppropriatenessRule)
WHERE r.name IN ['1.5.2', 'Rule: 1.5.2'] AND r.status = 'active'
RETURN r.id AS rule_id, r.logicJson AS logic_json
ORDER BY coalesce(r.updatedAt, r.createdAt) DESC
LIMIT 1
"""

_VERIFY = """
MATCH (r:AppropriatenessRule {id: $rule_id})
RETURN r.id AS rule_id, r.status AS status, r.logicJson AS logic_json
"""


@pytest.fixture(scope="module")
def kg_client():
    client = KnowledgeGraphClient()
    yield client
    client.close()


def test_persist_152_vulval_exclusions(kg_client) -> None:
    rows = kg_client.run(_FIND)
    assert rows, "No active NG12 1.5.2 rule"
    pred_id = rows[0]["rule_id"]
    raw = rows[0]["logic_json"]
    tree = json.loads(raw) if isinstance(raw, str) else raw
    updated = exclude_vulval_site_from_pelvic_leaf(tree)
    updates = RuleUpdates(
        name="Rule: 1.5.2",
        logic_tree=LogicNode.model_validate(updated),
    )
    result = apply_rule_edit(
        kg_client,
        predecessor_rule_id=pred_id,
        updates=updates,
        reviewer="live_persist_pytest",
        reason=(
            "Exclude vulval-site pain from the pelvic-pain leaf. "
            "NICE 1.5.2 is internal pelvic or abdominal pain."
        ),
    )
    new_id = result["rule_id"]
    assert new_id != pred_id
    verify = kg_client.run(_VERIFY, rule_id=new_id)
    assert verify
    saved = json.loads(verify[0]["logic_json"])
    patched = exclude_vulval_site_from_pelvic_leaf(saved)
    leaf = _pelvic_leaf(patched)
    assert VULVAL_PAIN_ID in leaf["excluded_concept_ids"]
    assert str(leaf.get("snomed_concept_id") or leaf.get("primary_concept_id")) == (
        PELVIC_PAIN_ID
    )


def _pelvic_leaf(node: dict) -> dict:
    if str(node.get("kind") or "").upper() == "CONCEPT":
        crit = node.get("criterion") or {}
        primary = str(crit.get("primary_concept_id") or crit.get("snomed_concept_id") or "")
        if primary == PELVIC_PAIN_ID:
            return crit
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found = _pelvic_leaf(child)
            if found:
                return found
    raise AssertionError("Pain in pelvis leaf missing")
