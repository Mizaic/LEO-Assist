"""Count patients with true cancer exclusion concepts."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

# Valid exclusion concepts -- 415068001 is actually "Exposure to UV light",
# NOT "No malignancy found on biopsy" -- it is a bad ID.
VALID_EXCLUSION_IDS = [
    "395100000",        # No evidence of cancer found (situation)
    "414861001",        # No evidence of recurrence of cancer (situation)
    "1090791000000103", # No evidence of malignancy (UK ext)
]
BAD_ID = "415068001"   # Exposure to ultraviolet radiation -- wrong concept

# IS_A-expand the valid ones
kg = KnowledgeGraphClient()
try:
    rows = kg.run(
        "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
        "WHERE ancestor.id IN $ids AND d.active = true "
        "RETURN d.id AS child_id",
        ids=VALID_EXCLUSION_IDS,
    )
    valid_pool = set(VALID_EXCLUSION_IDS) | {r["child_id"] for r in (rows or [])}
finally:
    kg.close()

pg = PatientGraphClient()
try:
    total = pg.run("MATCH (p:Patient) RETURN count(p) AS n")[0]["n"]

    # True exclusions via valid concepts
    true_excl = {
        r["pid"] for r in pg.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c) "
            "WHERE c.conceptId IN $ids "
            "RETURN DISTINCT toString(p.id) AS pid",
            ids=list(valid_pool),
        )
    }

    # False positives via bad concept ID
    false_excl = pg.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c) "
        "WHERE c.conceptId = $cid "
        "RETURN DISTINCT toString(p.id) AS pid, c.name AS name LIMIT 5",
        cid=BAD_ID,
    )

    # Exclusions via the domain's 395100000 specifically
    via_395 = {
        r["pid"] for r in pg.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c) "
            "WHERE c.conceptId = '395100000' "
            "RETURN DISTINCT toString(p.id) AS pid",
        )
    }

    via_414 = {
        r["pid"] for r in pg.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c) "
            "WHERE c.conceptId = '414861001' "
            "RETURN DISTINCT toString(p.id) AS pid",
        )
    }

    print(f"\nTotal patients:                          {total}")
    print(f"")
    print(f"TRUE cancer exclusion (valid concepts):  {len(true_excl)}")
    print(f"  395100000 No evidence of cancer found: {len(via_395)}")
    print(f"  414861001 No evidence of recurrence:   {len(via_414)}")
    print(f"")
    print(f"FALSE matches via 415068001 (UV light):  {len(false_excl)}")
    if false_excl:
        print(f"  This concept is '{false_excl[0]['name']}' -- bad ID in exclusion set")
    print(f"")
    print(f"  --> 415068001 should be REMOVED from CANCER_EXCLUSION_IDS")

finally:
    pg.close()
