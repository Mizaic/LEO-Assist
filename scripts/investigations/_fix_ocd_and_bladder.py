"""Fix two specific resolver errors found in spot-check:

1. OCD abbreviation resolves to Osteochondritis dissecans (82562007) instead of
   Obsessive-compulsive disorder (191736004). Needs a high-confidence surface form.

2. 'fast track referral for suspected bladder cancer' maps to gynaecological cancer.
   Bladder cancer is UROLOGICAL (276431000000102), not gynaecological.
   Also add prostate cancer, kidney cancer, testicular cancer to urological fast-track.

3. Other abbreviation fixes: BPAD -> bipolar, EUPD -> BPD, CMHT -> community MH team,
   SMI -> severe mental illness.
"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_UPSERT = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0,
    m.provenance  = 'audit-fix-spot-check-2026-04'
RETURN sf.normalized AS normalized, c.id AS concept_id, c.fsn AS concept_fsn
"""

_DELETE_WRONG = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $wrong_id})
DELETE m
RETURN count(m) AS deleted
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
RETURN c.id AS id, c.fsn AS fsn, m.confidence AS conf, m.provenance AS prov
ORDER BY m.confidence DESC
"""


def _norm(text: str) -> str:
    import re
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def upsert(s, form: str, concept_id: str) -> bool:
    normalized = _norm(form)
    r = s.run(_UPSERT, normalized=normalized, form=form, concept_id=concept_id).data()
    ok = bool(r)
    fsn = r[0]["concept_fsn"] if r else "?"
    print(f"  {'OK' if ok else 'FAIL'} upsert {form!r} -> {concept_id} | {fsn}")
    return ok


def delete_wrong(s, form: str, wrong_id: str) -> int:
    normalized = _norm(form)
    r = s.run(_DELETE_WRONG, normalized=normalized, wrong_id=wrong_id).data()
    n = r[0]["deleted"] if r else 0
    if n:
        print(f"  Deleted {n} wrong edge(s) for {form!r} -> {wrong_id}")
    return n


# (form, correct_concept_id, wrong_concept_id_to_delete_or_None)
FIXES = [
    # -- OCD abbreviation --
    # Term node "OCD" maps to Osteochondritis dissecans (82562007) in SNOMED.
    # A surface form with conf=1.0 beats Term nodes (1.2x boost).
    ("OCD",   "191736004", None),   # Obsessive-compulsive disorder
    ("ocd",   "191736004", None),

    # -- Other MH abbreviations that were KEPT (not in GCL, no surface form) --
    ("BPAD",  "13746004",  None),   # Bipolar disorder
    ("EUPD",  "20010003",  None),   # Emotionally unstable PD = BPD
    ("CMHT",  "304561000000109", None),  # Community mental health team care
    ("CRHTT", "304561000000109", None),  # Crisis resolution home treatment -> community MH
    ("SMI",   "75478009",  None),   # Severe mental illness
    ("NAD",   "17621005",  None),   # Normal (finding) -- frequently charted abbreviation

    # -- Eating disorder abbreviations --
    ("ARFID", "700213005", None),   # Avoidant restrictive food intake disorder
    ("ARBD",  "281004",    None),   # Alcohol-related dementia

    # -- Urology fast-track corrections --
    # "bladder cancer" fast-track was wrongly linked to gynaecological cancer;
    # delete that wrong edge and upsert the urological cancer fast-track.
    ("fast track referral for suspected bladder cancer",
        "276431000000102",  # Fast track referral for suspected urological cancer
        "276311000000101"),  # Wrong: gynaecological cancer -- delete this edge

    # Prostate fast-track: was linked to gynaecological, should be urological
    ("fast track referral for suspected prostate cancer",
        "276431000000102",  # Urological
        "276311000000101"),  # Wrong: gynaecological -- delete

    # Renal / kidney cancer -> urological
    ("fast track referral for suspected kidney cancer",  "276431000000102", None),
    ("fast track referral for suspected renal cancer",   "276431000000102", None),
    ("fast track referral for suspected testicular cancer", "276431000000102", None),
    ("fast track referral for suspected penile cancer",  "276431000000102", None),

    # Gynaecological -- correct aliases
    ("fast track referral for suspected ovarian cancer",   "276311000000101", None),
    ("fast track referral for suspected uterine cancer",   "276311000000101", None),
    ("fast track referral for suspected endometrial cancer","276311000000101", None),
    ("fast track referral for suspected vulval cancer",    "276311000000101", None),

    # -- Cervical cancer is gynaecological, not prostate --
    ("fast track referral for suspected cervical cancer",  "276311000000101", "276358001"),

    # -- Urgent/2WW referral for cancer (generic) --
    ("urgent referral for suspected cancer",   "306206005", None),  # Urgent referral
    ("2WW referral",                           "306206005", None),
    ("two week wait referral",                 "306206005", None),
    ("2 week wait referral",                   "306206005", None),
    ("two week wait",                          "306206005", None),

    # -- Common terms that need exact surface forms to beat noise --
    ("haemoptysis",          "66857006",  None),   # Hemoptysis (finding)
    ("hemoptysis",           "66857006",  None),
    ("rectal bleeding",      "405729008", None),   # Haematochezia
    ("PR bleeding",          "405729008", None),
    ("thrombocytosis",       "396333002", None),   # Thrombocytosis
    ("weight loss",          "89362005",  None),   # Weight loss finding
    ("unexplained weight loss", "89362005", None),
    ("PSA raised",           "396152005", None),   # PSA above reference range
    ("elevated PSA",         "396152005", None),
    ("raised PSA",           "396152005", None),
]


def main():
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
    ok_count = 0
    fail_count = 0

    with driver.session() as s:
        for entry in FIXES:
            form, cid, wrong_id = entry
            print(f"\nProcessing: {form!r}")

            # Delete wrong edge first if specified
            if wrong_id:
                delete_wrong(s, form, wrong_id)

            # Upsert correct mapping
            ok = upsert(s, form, cid)
            if ok:
                ok_count += 1
            else:
                fail_count += 1

            # Verify final state
            normalized = _norm(form)
            mappings = s.run(_CHECK, normalized=normalized).data()
            for m in mappings:
                tag = " <<< CORRECT" if m["id"] == cid else ""
                print(f"    Mapping: {m['id']} | {m['fsn']} conf={m['conf']}{tag}")

    driver.close()
    print(f"\n{'=' * 60}")
    print(f"Upserts OK: {ok_count}  Failed: {fail_count}")


if __name__ == "__main__":
    main()
