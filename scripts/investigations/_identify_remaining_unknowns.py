"""Identify the 17 remaining unknown-type completed episodes.

For each episode, shows:
- The patient ID
- The referral concept (if any)
- ALL diagnosis anchor concepts (the actual triggering codes)
- Whether those triggering codes are in our site-key lookup tables
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

from libs.neo4j_client.client import PatientGraphClient


def main() -> None:
    client = PatientGraphClient()

    # Get all unknown completed episodes with their referral and diagnosis anchors
    rows = client.run("""
        MATCH (ep:EpisodeOfCare)
        WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown'

        OPTIONAL MATCH (ref_enc:Encounter)-[r1:IS_PART_OF {milestone_type: 'referral'}]->(ep)
        OPTIONAL MATCH (ref_enc)-[:DOCUMENTS]->(ref_c)

        OPTIONAL MATCH (diag_enc:Encounter)-[r2:IS_PART_OF]->(ep)
        WHERE r2.milestone_type IN ['diagnosis', 'diagnosis_confirmed']
        OPTIONAL MATCH (diag_enc)-[:DOCUMENTS]->(diag_c)

        RETURN ep.episode_id AS ep_id,
               ep.patient_id AS patient_id,
               ep.referral_date AS ref_date,
               collect(DISTINCT {
                   cid: toString(ref_c.conceptId),
                   name: ref_c.name,
                   tag: ref_c.semanticTag
               }) AS ref_concepts,
               collect(DISTINCT {
                   cid: toString(diag_c.conceptId),
                   name: diag_c.name,
                   tag: diag_c.semanticTag
               }) AS diag_concepts
        ORDER BY ep.patient_id
    """)

    print(f"Unknown completed episodes: {len(rows)}")
    print("=" * 80)

    # Load the lookup tables
    import json

    site_by_id = {
        "276581000000102": "brain",
        "276341000000100": "breast",
        "254837009": "breast",
        "372130007": "melanoma",
        "399068003": "prostate",
        "93689003": "bladder",
        "363358000": "lung",
        "363495004": "leukaemia",
    }
    desc_map_path = (
        ROOT / "configs" / "snomed" / "snomed_cancer_type_descendant_site_map.json"
    )
    try:
        with open(desc_map_path) as f:
            desc_map = json.load(f).get("descendants", {})
    except FileNotFoundError:
        desc_map = {}

    for r in rows:
        ep_id = r.get("ep_id", "")
        patient_id = r.get("patient_id", "")
        ref_date = r.get("ref_date", "")
        ref_concepts = [
            c
            for c in (r.get("ref_concepts") or [])
            if c.get("cid") and c.get("cid") != "None"
        ]
        diag_concepts = [
            c
            for c in (r.get("diag_concepts") or [])
            if c.get("cid") and c.get("cid") != "None"
        ]

        # Deduplicate by cid
        ref_by_cid = {c["cid"]: c for c in ref_concepts}
        diag_by_cid = {c["cid"]: c for c in diag_concepts}

        print(f"\nPatient: {patient_id}  Referral: {ref_date}")
        print(f"  Referral codes:")
        for c in ref_by_cid.values():
            cid = c["cid"]
            name = c.get("name", "?")
            in_map = "(in _SITE_BY_CONCEPT_ID)" if cid in site_by_id else ""
            print(f"    {cid}: {name} {in_map}")

        print(f"  Diagnosis codes (in diagnosis-typed encounters):")
        for c in diag_by_cid.values():
            cid = c["cid"]
            name = c.get("name", "?")
            tag = c.get("tag", "")
            in_site = site_by_id.get(cid)
            in_desc = desc_map.get(cid)
            coverage = (
                f"-> {in_site}"
                if in_site
                else (f"-> {in_desc} (desc)" if in_desc else "NOT IN LOOKUP")
            )
            flag = " *** UNRESOLVED NUMERIC NAME ***" if name == cid else ""
            print(f"    {cid}: {name} [{tag}] {coverage}{flag}")

    client.close()


if __name__ == "__main__":
    main()
