"""Live persist: exclude vulval-site codes from NG12 1.7.4.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_ng12_174_live_persist.py -v

Atlas: UN-5F3BF083, DI-CDDA5214.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from libs.guidelines.ng12_174_vulval_skin import (
    ERUPTION_OF_SKIN_ID,
    SKIN_LESION_ID,
    VULVAL_MELANOTIC_MACULE_ID,
    exclude_vulval_site_from_skin_lesion_leaf,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from services.api.app.services.guidance_rule_edit import (
    LogicNode,
    RuleUpdates,
    apply_rule_edit,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write the 1.7.4 exclusion.",
)

_FIND = """
MATCH (r:AppropriatenessRule)
WHERE r.name IN ['1.7.4', 'Rule: 1.7.4'] AND r.status = 'active'
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
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    client = KnowledgeGraphClient()
    yield client
    client.close()


def test_persist_174_vulval_exclusions(kg_client) -> None:
    rows = kg_client.run(_FIND)
    assert rows, "No active NG12 1.7.4 rule"
    pred_id = rows[0]["rule_id"]
    raw = rows[0]["logic_json"]
    tree = json.loads(raw) if isinstance(raw, str) else raw
    updated = exclude_vulval_site_from_skin_lesion_leaf(tree)
    updates = RuleUpdates(
        name="Rule: 1.7.4",
        logic_tree=LogicNode.model_validate(updated),
    )
    result = apply_rule_edit(
        kg_client,
        predecessor_rule_id=pred_id,
        updates=updates,
        reviewer="live_persist_pytest",
        reason=(
            "Exclude eruption of skin and vulval-site disorders from the "
            "Skin lesion leaf. NICE 1.7.4 is cutaneous SCC suspicion, "
            "not a rash and not vulval cancer (1.5.17)."
        ),
    )
    new_id = result["rule_id"]
    assert new_id != pred_id
    verify = kg_client.run(_VERIFY, rule_id=new_id)
    assert verify
    saved = json.loads(verify[0]["logic_json"])
    leaf = _skin_leaf(saved)
    assert VULVAL_MELANOTIC_MACULE_ID in leaf["excluded_concept_ids"]
    assert ERUPTION_OF_SKIN_ID in leaf["excluded_concept_ids"]
    assert str(leaf.get("snomed_concept_id") or leaf.get("primary_concept_id")) == (
        SKIN_LESION_ID
    )


def _skin_leaf(node: dict) -> dict:
    if str(node.get("kind") or "").upper() == "CONCEPT":
        crit = node.get("criterion") or {}
        primary = str(
            crit.get("primary_concept_id") or crit.get("snomed_concept_id") or ""
        )
        if primary == SKIN_LESION_ID:
            return crit
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found = _skin_leaf(child)
            if found:
                return found
    raise AssertionError("Skin lesion leaf missing")
