"""Find surface form schema and check 395100000 surface form mappings."""

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

CONCEPT_ID = 395100000

SCREENING_PATTERNS = [
    "cervical smear",
    "cervical cytology",
    "smear negative",
    "hpv not detected",
    "hpv test",
    "high risk hpv",
    "negative fit",
    "fobt",
    "faecal",
    "overall negative",
    "bowel cancer screening",
    "normal recall",
    "no cytology",
    "cytology normal",
    "cytology negative",
    "cytology laboratory",
    "screening negative",
]


def is_screening(text):
    tl = (text or "").lower()
    return any(p in tl for p in SCREENING_PATTERNS)


client = PatientGraphClient()
with client.session() as s:
    # Find labels containing "surface"
    lbl_rows = list(s.run("CALL db.labels() YIELD label RETURN label"))
    surface_labels = [r["label"] for r in lbl_rows if "surface" in r["label"].lower()]
    print("Surface-related node labels:", surface_labels)

    # Sample a SurfaceForm node
    sample = s.run("MATCH (sf:SurfaceForm) RETURN sf LIMIT 1").single()
    if sample:
        print("\nSurfaceForm sample keys:", list(dict(sample["sf"]).keys()))
        print(
            "SurfaceForm sample:",
            {k: v for k, v in dict(sample["sf"]).items() if k != "embedding"},
        )

    # Check all surface forms pointing to Situation nodes (395100000 is a Situation)
    sits = list(
        s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Situation) "
            "RETURN sf.form AS form, sf.normalized AS norm, c.conceptId AS cid, c.name AS name "
            "LIMIT 50"
        )
    )
    print(f"\nSurfaceForm->Situation mappings (up to 50): {len(sits)}")

    # Specifically find any SF mapped to 395100000
    specific = list(
        s.run(
            "MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c) "
            "WHERE c.conceptId = $cid "
            "RETURN sf.form AS form, sf.normalized AS norm, sf.source AS src, id(sf) AS nid",
            cid=CONCEPT_ID,
        )
    )
    print(f"\nSurface forms for conceptId={CONCEPT_ID}: {len(specific)}")
    bad = []
    for r in specific:
        form = r.get("form") or r.get("norm") or ""
        flag = "[BAD]" if is_screening(form) else "[OK ]"
        print(f"  {flag} {form!r}  src={r['src']}")
        if is_screening(form):
            bad.append({"nid": r["nid"], "form": form})

    # Also look at Situation nodes directly via name
    no_cancer_nodes = list(
        s.run(
            "MATCH (c:Situation) WHERE c.conceptId = $cid "
            "OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c) "
            "RETURN c.name AS name, count(sf) AS sf_count",
            cid=CONCEPT_ID,
        )
    )
    print(f"\nNo-evidence-of-cancer node(s):")
    for r in no_cancer_nodes:
        print(f"  name={r['name']}  surface_forms={r['sf_count']}")

    if bad:
        print(f"\nFOUND {len(bad)} bad surface form(s) to delete.")
        for item in bad:
            print(f"  Deleting node id={item['nid']} form={item['form']!r} ...")
            s.run("MATCH (sf) WHERE id(sf) = $nid DETACH DELETE sf", nid=item["nid"])
            print(f"  Deleted.")
    else:
        print("\nNo bad surface forms found -- all clean.")

client.close()
