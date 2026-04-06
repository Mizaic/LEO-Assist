"""Check Neo4j directly for surface forms mapped to 395100000."""
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
    "cervical smear", "cervical cytology", "smear negative", "hpv not detected",
    "hpv test", "high risk hpv", "negative fit", "fobt", "faecal",
    "overall negative", "bowel cancer screening", "normal recall",
    "no cytology", "cytology normal", "cytology negative", "cytology laboratory",
    "screening negative", "negative result",
]


def is_screening(text: str) -> bool:
    tl = (text or "").lower()
    return any(p in tl for p in SCREENING_PATTERNS)


client = PatientGraphClient()
with client.session() as s:
    # Try MAPS_TO relationship
    rows_maps = list(s.run(
        "MATCH (sf)-[:MAPS_TO]->(c) WHERE c.conceptId = $cid "
        "RETURN sf.form AS form, sf.normalized AS norm, sf.source AS src, id(sf) AS nid",
        cid=CONCEPT_ID,
    ))

    # Try HAS_SURFACE_FORM relationship
    rows_hsf = list(s.run(
        "MATCH (c)-[:HAS_SURFACE_FORM]->(sf) WHERE c.conceptId = $cid "
        "RETURN sf.form AS form, sf.normalized AS norm, sf.source AS src, id(sf) AS nid",
        cid=CONCEPT_ID,
    ))

    # Try SurfaceFormMapping label
    rows_sfm = list(s.run(
        "MATCH (sf:SurfaceFormMapping) WHERE sf.concept_id = $cid OR sf.snomed_concept_id = $cid "
        "RETURN sf.form AS form, sf.normalized AS norm, sf.source AS src, id(sf) AS nid",
        cid=str(CONCEPT_ID),
    ))

    # Widen: any node with a form property that also has a property pointing to 395100000
    rows_wide = list(s.run("""
        MATCH (sf)
        WHERE (sf.concept_id = '395100000' OR sf.snomed_concept_id = '395100000'
               OR sf.target_concept_id = '395100000')
          AND EXISTS { MATCH (sf) WHERE sf.form IS NOT NULL OR sf.normalized IS NOT NULL }
        RETURN sf.form AS form, sf.normalized AS norm, sf.source AS src, labels(sf) AS lbl
        LIMIT 50
    """))

    # Check how the terminology service stores surface forms - find any node by concept
    schema_check = list(s.run("""
        MATCH (c {conceptId: $cid})
        OPTIONAL MATCH (c)-[r]-(n)
        RETURN type(r) AS rel, labels(n) AS nlabels, keys(n) AS nkeys
        LIMIT 5
    """, cid=CONCEPT_ID))

client.close()

all_forms = rows_maps + rows_hsf + rows_sfm + rows_wide
print(f"Surface forms via MAPS_TO        : {len(rows_maps)}")
print(f"Surface forms via HAS_SURFACE_FORM: {len(rows_hsf)}")
print(f"Surface forms via property match  : {len(rows_sfm)}")
print(f"Surface forms via wide search     : {len(rows_wide)}")
print(f"Total unique                      : {len(all_forms)}")
print()

if all_forms:
    bad = []
    ok  = []
    for r in all_forms:
        form = r.get("form") or r.get("norm") or ""
        if is_screening(form):
            bad.append(form)
        else:
            ok.append(form)
    print(f"Clean forms ({len(ok)}):")
    for f in ok:
        print(f"  [OK ] {f!r}")
    print(f"\nScreening false positives ({len(bad)}):")
    for f in bad:
        print(f"  [BAD] {f!r}")
else:
    print("No surface forms found via graph queries.")

print()
print("Schema check (relationships on the concept node):")
for r in schema_check:
    print(f"  rel={r['rel']}  labels={r['nlabels']}  keys={r['nkeys']}")
