"""Data fix for patient 7306752529 (Farshid Ershadi - Thyroid Carcinoma).

Root cause: The EMIS code XaMkD ('Fast track referral for suspected head and
neck cancer', SNOMED 276401000000108) was not mapped to a Situation node in
Neo4j.  The 2WW referral dated 2024-03-07 therefore had no DOCUMENTS
relationship pointing to the SNOMED concept, so the remediation script
classified this patient as no_referral.

This script:
  1. Audits the current state of the relevant encounters.
  2. Ensures the Situation node for 276401000000108 exists in the graph.
  3. Creates the DOCUMENTS relationship on encounter 281ce94e-... (the PRISM
     referral entry) if it is missing.
  4. Updates the EpisodeOfCare to reflect the correct referral date and site.

Run dry-run first, then --apply.
"""

from __future__ import annotations

import argparse
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from neo4j import GraphDatabase  # noqa: E402

_KV_URL = os.getenv("AZURE_KEYVAULT_URL", "")

PATIENT_ID = "7306752529"
# The PRISM 2WW encounter on 2024-03-07 that contains the referral coding.
# EMIS code XaMkD maps to SNOMED 280521000000108 (verified via terminology server).
# NOTE: 276401000000108 is colorectal cancer referral -- do NOT use that here.
REFERRAL_ENCOUNTER_ID = "281ce94e-24e7-40e2-b66b-1f2e00b050a3"
REFERRAL_DATE = "2024-03-07"
SNOMED_CONCEPT_ID = 280521000000108
SNOMED_NAME = "Fast track referral for suspected head and neck cancer"
SNOMED_TAG = "procedure"
EPISODE_ID = "cfd597d2606503ff"


def _load_secrets() -> dict[str, str]:
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "")
    pw = os.getenv("NEO4J_PASSWORD", "")
    if uri and user and pw:
        return {"uri": uri, "user": user, "password": pw}
    if not _KV_URL:
        raise EnvironmentError("Set AZURE_KEYVAULT_URL or NEO4J_* env vars")
    cred = DefaultAzureCredential()
    kv = SecretClient(vault_url=_KV_URL, credential=cred)
    return {
        "uri": kv.get_secret("NEO4J-URI").value,
        "user": kv.get_secret("NEO4J-USER").value,
        "password": kv.get_secret("NEO4J-PASSWORD").value,
    }


# ---------------------------------------------------------------------------
# Audit queries
# ---------------------------------------------------------------------------

_Q_ENCOUNTER_CHECK = """
MATCH (e:Encounter)
WHERE toString(e.id) = $eid
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(d)
  WHERE toString(d.conceptId) = $cid
RETURN
    e.id   AS encounter_id,
    e.date AS encounter_date,
    count(r) AS existing_referral_rels
"""

_Q_EPISODE_CHECK = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
RETURN
    ep.episode_id    AS episode_id,
    ep.referral_site AS referral_site,
    ep.condition_type AS condition_type,
    ep.referral_date  AS referral_date,
    ep.status         AS status,
    ep.flags          AS flags
"""

# ---------------------------------------------------------------------------
# Fix queries
# ---------------------------------------------------------------------------

_Q_ENSURE_SITUATION_NODE = """
MERGE (d:Situation {conceptId: $conceptId})
ON CREATE SET
    d.name        = $name,
    d.semanticTag = $tag,
    d.source      = 'manual_fix'
RETURN d.conceptId AS concept_id
"""

_Q_ADD_DOCUMENTS_REL = """
MATCH (e:Encounter)
WHERE toString(e.id) = $eid
MATCH (d:Situation {conceptId: $conceptId})
MERGE (e)-[r:DOCUMENTS]->(d)
ON CREATE SET
    r.assertion  = 'present',
    r.source     = 'EMIS_CODE_XaMkD',
    r.confidence = 1.0,
    r.added_by   = 'fix_7306752529.py'
RETURN type(r) AS rel_type
"""

_Q_UPDATE_EPISODE = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET
    ep.referral_date            = $referral_date,
    ep.last_referral_date       = $referral_date,
    ep.first_presentation_date  = $referral_date,
    ep.referral_site            = 'head_and_neck',
    ep.condition_type           = 'head_and_neck',
    ep.cancer_type              = 'head_and_neck',
    ep.referral_encounter_ids   = $referral_encounter_id,
    ep.flags                    = 'SITE_FIX_APPLIED',
    ep.needs_review             = false,
    ep.updated_at               = datetime()
RETURN ep.episode_id AS episode_id
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Apply fixes (omit for dry-run)")
    args = ap.parse_args()

    secrets = _load_secrets()
    driver = GraphDatabase.driver(
        secrets["uri"],
        auth=(secrets["user"], secrets["password"]),
    )

    with driver.session() as session:
        print(f"\n=== Fix audit for patient {PATIENT_ID} ===\n")

        enc = session.run(
            _Q_ENCOUNTER_CHECK,
            eid=REFERRAL_ENCOUNTER_ID,
            cid=str(SNOMED_CONCEPT_ID),
        ).single()
        if enc:
            print(f"Encounter {REFERRAL_ENCOUNTER_ID}")
            print(f"  date                   : {enc['encounter_date']}")
            print(f"  existing referral rels : {enc['existing_referral_rels']}")
        else:
            print(f"WARNING: Encounter {REFERRAL_ENCOUNTER_ID} not found!")

        ep = session.run(
            _Q_EPISODE_CHECK,
            episode_id=EPISODE_ID,
        ).single()
        if ep:
            print(f"\nEpisodeOfCare {EPISODE_ID}")
            print(f"  referral_site  : {ep['referral_site']}")
            print(f"  condition_type : {ep['condition_type']}")
            print(f"  referral_date  : {ep['referral_date']}")
            print(f"  status         : {ep['status']}")
            print(f"  flags          : {ep['flags']}")
        else:
            print(f"\nWARNING: EpisodeOfCare {EPISODE_ID} not found!")

        if not args.apply:
            print("\nDRY-RUN complete.  Re-run with --apply to apply fixes.")
            driver.close()
            return

        print("\nApplying fixes...")

        # 1. Ensure Situation node exists
        session.run(
            _Q_ENSURE_SITUATION_NODE,
            conceptId=SNOMED_CONCEPT_ID,
            name=SNOMED_NAME,
            tag=SNOMED_TAG,
        )
        print(f"  Situation node {SNOMED_CONCEPT_ID} ensured.")

        # 2. Add DOCUMENTS relationship
        result = session.run(
            _Q_ADD_DOCUMENTS_REL,
            eid=REFERRAL_ENCOUNTER_ID,
            conceptId=SNOMED_CONCEPT_ID,
        ).single()
        if result:
            print(f"  DOCUMENTS relationship created: {result['rel_type']}")
        else:
            print("  WARNING: DOCUMENTS relationship not created -- check encounter ID.")

        # 3. Update EpisodeOfCare
        ep_result = session.run(
            _Q_UPDATE_EPISODE,
            episode_id=EPISODE_ID,
            referral_date=REFERRAL_DATE,
            referral_encounter_id=REFERRAL_ENCOUNTER_ID,
        ).single()
        if ep_result:
            print(f"  EpisodeOfCare {ep_result['episode_id']} updated.")
        else:
            print("  WARNING: EpisodeOfCare not updated -- check episode ID.")

        print("\nFix complete. Verify by re-reading the episode or running the")
        print("remediation script with --patient-ids 7306752529.")

    driver.close()


if __name__ == "__main__":
    main()
