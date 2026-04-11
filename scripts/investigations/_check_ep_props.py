import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv("secrets/.env.config", override=False)
load_dotenv("secrets/.env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

c = PatientGraphClient()
with c.session() as s:
    r = s.run("MATCH (ep:EpisodeOfCare) RETURN keys(ep) AS k LIMIT 1").data()
    print("Episode keys:", r[0]["k"] if r else "none")

    r2 = s.run(
        "MATCH (ep:EpisodeOfCare) WHERE ep.status = 'completed' RETURN ep LIMIT 1"
    ).data()
    if r2:
        ep = dict(r2[0]["ep"])
        for k, v in sorted(ep.items()):
            print(f"  {k}: {v}")

    r3 = s.run(
        "MATCH (ep:EpisodeOfCare)<-[r:IS_PART_OF]-(e:Encounter) RETURN keys(r) AS rk, r.milestone_type AS mt LIMIT 3"
    ).data()
    print("IS_PART_OF rel props:", r3)

    # What does the episode store for diagnosis?
    r4 = s.run("""
        MATCH (ep:EpisodeOfCare) WHERE ep.status = 'completed'
        RETURN ep.cancer_diagnosis_date AS dd, ep.cancer_diagnosis_concept AS dc,
               ep.end_date AS ed, ep.cancer_type AS ct
        LIMIT 5
    """).data()
    print("Completed ep diagnosis fields:", r4)
c.close()
