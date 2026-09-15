"""Live persist: seed the shared pelvic ultrasound InvestigationFamily.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_investigation_family_live_persist.py -v

Atlas: DI-B3B44F09.
"""

from __future__ import annotations

import os

import pytest

from libs.guidelines.investigation_family_catalog import (
    FETCH_INVESTIGATION_FAMILIES,
    PELVIC_US_FAMILY_ID,
    PELVIC_US_FAMILY_NAME,
    PELVIC_US_MEMBER_IDS,
    family_ids_for_concept,
    index_family_rows,
    seed_investigation_family,
)
from libs.neo4j_client.client import KnowledgeGraphClient

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_GUIDANCE") != "1",
    reason="Set LIVE_NEO4J_GUIDANCE=1 to write InvestigationFamily.",
)


@pytest.fixture(scope="module")
def kg_client():
    client = KnowledgeGraphClient()
    yield client
    client.close()


def test_persist_pelvic_us_investigation_family(kg_client) -> None:
    kg_client.run(
        "CREATE CONSTRAINT investigation_family_id IF NOT EXISTS "
        "FOR (f:InvestigationFamily) REQUIRE f.id IS UNIQUE"
    )
    rows = seed_investigation_family(
        kg_client,
        family_id=PELVIC_US_FAMILY_ID,
        name=PELVIC_US_FAMILY_NAME,
        member_ids=PELVIC_US_MEMBER_IDS,
    )
    assert rows
    assert rows[0]["linked"] == len(PELVIC_US_MEMBER_IDS)
    fetched = kg_client.run(FETCH_INVESTIGATION_FAMILIES)
    index = index_family_rows(fetched)
    members = family_ids_for_concept("418394000", index)
    assert members == set(PELVIC_US_MEMBER_IDS)
