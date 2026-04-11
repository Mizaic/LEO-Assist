"""Find what concept IDs are ACTUALLY in the diagnosis ValueSet bucket
for unknown-type completed episodes.

This queries the KG to find which domains contain the concept IDs appearing
in IS_PART_OF diagnosis encounters, and checks which ones are actually the
diagnosis-bucket triggers (vs noise from co-coded encounter concepts).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient


def main() -> None:
    pkg = PatientGraphClient()
    kgc = KnowledgeGraphClient()

    # Step 1: get all concept IDs that appear in diagnosis-type encounters
    # for unknown-completed episodes
    ep_rows = pkg.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "RETURN ep.episode_id AS episode_id "
        "LIMIT 200"
    )
    ep_ids = [r["episode_id"] for r in ep_rows]
    print(f"Unknown completed episodes: {len(ep_ids)}")

    anchor_rows = pkg.run(
        "UNWIND $ep_ids AS eid "
        "MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: eid}) "
        "WHERE r.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "OPTIONAL MATCH (enc)-[:DOCUMENTS]->(c) "
        "RETURN DISTINCT toString(c.conceptId) AS concept_id, c.name AS name",
        ep_ids=ep_ids,
    )
    cids = [r["concept_id"] for r in anchor_rows if r.get("concept_id")]
    print(f"Distinct concept IDs in their diagnosis encounters: {len(cids)}")

    # Step 2: check which of these are in the cancer_types OR stage_of_diagnosis domain
    vs_rows = kgc.run(
        "MATCH (vs:ValueSet)-[:CONTAINS]->(c) "
        "WHERE vs.domain IN ['cancer_types', 'stage_of_diagnosis'] "
        "  AND toString(c.conceptId) IN $ids "
        "RETURN vs.domain AS domain, "
        "       toString(c.conceptId) AS concept_id, "
        "       c.name AS name "
        "ORDER BY domain, concept_id",
        ids=cids,
    )
    if not vs_rows:
        print(
            "None of the co-coded concept IDs found in cancer_types or stage_of_diagnosis ValueSets."
        )
        print("Checking if the KG uses FHIR ValueSet structure instead...")

        # Try FHIR ValueSet structure
        fhir_rows = kgc.run(
            "MATCH (vs:FHIRValueSet)-[:INCLUDES]->(c) "
            "WHERE vs.id IN ['cancer_types', 'stage_of_diagnosis'] "
            "  AND toString(c.conceptId) IN $ids "
            "RETURN vs.id AS domain, toString(c.conceptId) AS concept_id, c.name AS name "
            "LIMIT 20",
            ids=cids,
        )
        if fhir_rows:
            for r in fhir_rows:
                print(f"  FHIR: {r['domain']}: {r['concept_id']}: {r['name']}")
        else:
            print("  Not found in FHIR structure either.")
    else:
        print(f"\n{'domain':<25} {'concept_id':<17} name")
        print("-" * 70)
        for r in vs_rows:
            d = r.get("domain", "")
            cid = r.get("concept_id", "")
            name = str(r.get("name") or "")[:40]
            print(f"{d:<25} {cid:<17} {name}")

    # Step 3: check how the domain registry is loaded at runtime to see what
    # concept IDs end up in the diagnosis bucket
    print("\n=== Checking KG ValueSet nodes for domain=cancer_types ===")
    ct_rows = kgc.run(
        "MATCH (vs:ValueSet {domain: 'cancer_types'}) "
        "RETURN vs.domain AS domain, keys(vs) AS props "
        "LIMIT 3"
    )
    if not ct_rows:
        print(
            "  No ValueSet nodes with domain='cancer_types' found. Trying FHIRValueSet..."
        )
        fhir_vs = kgc.run(
            "MATCH (vs) WHERE vs.domain = 'cancer_types' "
            "RETURN labels(vs) AS labels, keys(vs) AS props LIMIT 3"
        )
        for r in fhir_vs:
            print(f"  labels={r['labels']}  props={r['props']}")
    else:
        for r in ct_rows:
            print(f"  {r}")

    # Step 4: look for where concept IDs 10743008 and 254701007 come from
    print("\n=== Checking remaining unresolved IDs in stage_of_diagnosis ===")
    stage_rows = kgc.run(
        "MATCH (vs:ValueSet {domain: 'stage_of_diagnosis'})-[:CONTAINS]->(c) "
        "RETURN toString(c.conceptId) AS concept_id, c.name AS name "
        "LIMIT 20"
    )
    if stage_rows:
        print("stage_of_diagnosis ValueSet entries (sample):")
        for r in stage_rows:
            print(f"  {r['concept_id']}: {r['name']}")
    else:
        print("  No stage_of_diagnosis ValueSet found with :CONTAINS pattern.")

    pkg.close()
    kgc.close()


if __name__ == "__main__":
    main()
