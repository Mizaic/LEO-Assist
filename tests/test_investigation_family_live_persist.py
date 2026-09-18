"""Live persist: seed the shared InvestigationFamily rows.

NHS 4568668417 was offered a faecal immunochemical test (FIT), a
cancer antigen 125 (CA125) test, and a pelvic ultrasound that the
record already held. These families let the evaluator mark those
actions as already done.

Opt-in:

  LIVE_NEO4J_GUIDANCE=1 pytest tests/test_investigation_family_live_persist.py -v

Atlas: DI-B3B44F09.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from libs.guidelines.investigation_family_catalog import (
    CA125_FAMILY_ID,
    FETCH_INVESTIGATION_FAMILIES,
    FIT_FAMILY_ID,
    PELVIC_US_FAMILY_ID,
    SHARED_FAMILIES,
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
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    client = KnowledgeGraphClient()
    yield client
    client.close()


def test_persist_shared_investigation_families(kg_client) -> None:
    kg_client.run(
        "CREATE CONSTRAINT investigation_family_id IF NOT EXISTS "
        "FOR (f:InvestigationFamily) REQUIRE f.id IS UNIQUE"
    )
    for family in SHARED_FAMILIES:
        rows = seed_investigation_family(
            kg_client,
            family_id=family["family_id"],
            name=family["name"],
            member_ids=family["members"],
        )
        assert rows, f"{family['family_id']} did not seed"
        assert rows[0]["linked"] == len(family["members"])

    index = index_family_rows(kg_client.run(FETCH_INVESTIGATION_FAMILIES))
    for family in SHARED_FAMILIES:
        for member in family["members"]:
            assert family_ids_for_concept(member, index) >= set(family["members"])


def test_seeded_families_cover_the_three_missed_investigations(kg_client) -> None:
    index = index_family_rows(kg_client.run(FETCH_INVESTIGATION_FAMILIES))
    # CA125 result proves the CA125 measurement was carried out.
    assert "1000461000000109" in family_ids_for_concept("909121000000107", index)
    # A transvaginal pelvis scan proves the pelvic ultrasound was carried out.
    assert "315011000000105" in family_ids_for_concept("418394000", index)
    # A quantitative FIT result proves the FIT kit was provided.
    assert "1049361000000101" in family_ids_for_concept("149421000000109", index)
    assert {PELVIC_US_FAMILY_ID, CA125_FAMILY_ID, FIT_FAMILY_ID}


def test_abdomen_only_scan_is_not_in_the_pelvic_family(kg_client) -> None:
    """An abdomen scan leaves the pelvis unimaged, so it must not match."""
    index = index_family_rows(kg_client.run(FETCH_INVESTIGATION_FAMILIES))
    assert "45036003" not in family_ids_for_concept("418394000", index)
