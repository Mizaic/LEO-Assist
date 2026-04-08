"""Find which ValueSet domain contains 10743008 and 78873005 in the KG."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient

TARGETS = ["10743008", "78873005"]


def main() -> None:
    kg = KnowledgeGraphClient()

    # Step 1: find ValueSet nodes and their structure
    vs_labels = kg.run(
        "MATCH (v:ValueSet) RETURN DISTINCT labels(v) AS lbl, keys(v) AS props LIMIT 3"
    )
    print("=== ValueSet node structure ===")
    for r in vs_labels:
        print(f"  {r}")

    print()
    # Step 2: look at the rawJson for the cancer_types and stage_of_diagnosis ValueSets
    vs_rows = kg.run(
        "MATCH (v:ValueSet) "
        "WHERE v.domain IN ['cancer_types', 'stage_of_diagnosis'] "
        "   OR v.id IN ['ncda-cancer_types', 'ncda-stage_of_diagnosis'] "
        "RETURN v.id AS id, v.domain AS domain, v.milestoneType AS mt, "
        "       substring(toString(v.rawJson), 0, 300) AS raw_preview "
        "LIMIT 5"
    )
    print("=== cancer_types / stage_of_diagnosis ValueSet rows ===")
    if not vs_rows:
        print("  None found with domain/id filter.")
    for r in vs_rows:
        print(f"  id={r['id']} domain={r['domain']} mt={r['mt']}")
        print(f"  raw_preview: {r['raw_preview'][:200]}")

    print()
    # Step 3: check if target IDs appear in any ValueSet's rawJson
    all_vs = kg.run(
        "MATCH (v:ValueSet) "
        "WHERE v.rawJson CONTAINS $t1 OR v.rawJson CONTAINS $t2 "
        "RETURN v.id AS id, v.domain AS domain, v.milestoneType AS mt",
        t1=TARGETS[0],
        t2=TARGETS[1],
    )
    print("=== ValueSets whose rawJson contains 10743008 or 78873005 ===")
    if not all_vs:
        print("  Neither ID found in any ValueSet rawJson.")
    for r in all_vs:
        print(f"  {r}")

    print()
    # Step 4: check direct cancer_types IS_A expansion descendants
    isa_check = kg.run(
        "MATCH (parent:Concept)<-[:IS_A*1..5]-(d:Concept) "
        "WHERE parent.id IN ['254837009','372130007','399068003','363358000'] "
        "  AND d.id IN $targets "
        "RETURN parent.id AS parent_id, d.id AS child_id, d.preferredTerm AS term",
        targets=TARGETS,
    )
    print("=== IS_A descendant check for target IDs ===")
    if not isa_check:
        print("  Targets are NOT IS_A descendants of common cancer type concepts.")
    for r in isa_check:
        print(f"  parent={r['parent_id']} -> child={r['child_id']} ({r['term']})")

    kg.close()


if __name__ == "__main__":
    main()
