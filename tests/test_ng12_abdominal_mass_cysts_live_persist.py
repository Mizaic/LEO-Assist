"""Live persist: exclude organ cysts from NG12 1.3.1 and 1.5.1.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest \\
    tests/test_ng12_abdominal_mass_cysts_live_persist.py -v

Atlas: UN-5F3BF083, DI-CDDA5214, DO-51F0FE8C, VT-0AD6DA01.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from libs.guidelines.ng12_abdominal_mass_cysts import (
    ABDOMINAL_MASS_ID,
    CYST_OF_KIDNEY_ID,
    CYST_OF_PANCREAS_ID,
    exclude_organ_cysts_from_abdominal_mass_leaf,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from services.api.app.services.guidance_rule_edit import (
    LogicNode,
    RuleUpdates,
    apply_rule_edit,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write the mass cyst exclusions.",
)

_FIND = """
MATCH (r:AppropriatenessRule)
WHERE r.name = $name AND r.status = 'active'
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
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "secrets" / ".env")
    load_dotenv(root / ".env")
    client = KnowledgeGraphClient()
    yield client
    client.close()


@pytest.mark.parametrize("name", ["Rule: 1.3.1", "Rule: 1.5.1"])
def test_persist_abdominal_mass_cyst_exclusions(kg_client, name: str) -> None:
    rows = kg_client.run(_FIND, name=name)
    assert rows, f"No active {name} rule"
    pred_id = rows[0]["rule_id"]
    raw = rows[0]["logic_json"]
    tree = json.loads(raw) if isinstance(raw, str) else raw
    updated = exclude_organ_cysts_from_abdominal_mass_leaf(tree)
    updates = RuleUpdates(
        name=name,
        logic_tree=LogicNode.model_validate(updated),
    )
    result = apply_rule_edit(
        kg_client,
        predecessor_rule_id=pred_id,
        updates=updates,
        reviewer="live_persist_pytest",
        reason=(
            "Exclude cyst of pancreas and cyst of kidney from the "
            "abdominal-mass leaf. NICE 1.3.1 and 1.5.1 are not organ cysts."
        ),
    )
    new_id = result["rule_id"]
    assert new_id != pred_id
    verify = kg_client.run(_VERIFY, rule_id=new_id)
    assert verify
    saved = json.loads(verify[0]["logic_json"])
    leaves = _mass_leaves(saved)
    assert leaves
    for leaf in leaves:
        assert CYST_OF_PANCREAS_ID in leaf["excluded_concept_ids"]
        assert CYST_OF_KIDNEY_ID in leaf["excluded_concept_ids"]


def _mass_leaves(node: dict) -> list[dict]:
    found: list[dict] = []
    if str(node.get("kind") or "").upper() == "CONCEPT":
        crit = node.get("criterion") or {}
        cid = crit.get("primary_concept_id") or crit.get(
            "snomed_concept_id"
        )
        primary = str(cid or "")
        if primary == ABDOMINAL_MASS_ID:
            found.append(crit)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found.extend(_mass_leaves(child))
    return found
